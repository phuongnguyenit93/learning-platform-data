# Tổng quát hóa, chuyên biệt hóa và tiêu chí chia kiểu con

## Mục tiêu bài học

Sau bài này, bạn có thể giải thích **tổng quát hóa (generalization)** và **chuyên biệt hóa (specialization)** trong mô hình dữ liệu; xác định khi nào nhiều thực thể nên chia sẻ một kiểu cha (supertype) và khi nào cần các kiểu con (subtype); viết tiêu chí thành viên của từng kiểu con; phân biệt hai ràng buộc độc lập là disjoint/overlapping và total/partial; đồng thời đánh giá cách biểu diễn phân cấp trong mô hình quan hệ.

Bạn cũng sẽ biết cách tránh tạo kiểu con chỉ vì khác màn hình hoặc khác vài thuộc tính, cách xử lý một đối tượng có thể đổi loại theo thời gian, và cách kiểm chứng phân cấp bằng dữ liệu cùng quy tắc nghiệp vụ.

## 1. Vì sao cần mô hình hóa phân cấp?

Trong một miền nghiệp vụ, nhiều loại đối tượng có thể có những thuộc tính và hành vi chung, nhưng vẫn có những đặc điểm riêng.

Ví dụ trong hệ thống nhân sự:

- Nhân viên toàn thời gian có mã nhân viên, họ tên, ngày vào làm và phòng ban.
- Nhà thầu cũng có mã hồ sơ, họ tên, ngày bắt đầu hợp đồng và đơn vị phụ trách.
- Cả hai đều là người làm việc cho tổ chức, nhưng loại quan hệ lao động, chính sách phúc lợi và cách kết thúc hợp đồng khác nhau.

Nếu lưu hai loại này hoàn toàn tách biệt, thông tin chung có thể bị lặp lại và việc tìm tất cả người đang làm việc trở nên khó khăn. Nếu gộp mọi thứ vào một thực thể mà không phân biệt loại, các quy tắc riêng có thể bị trộn lẫn và nhiều trường trở thành NULL hoặc mang ý nghĩa không rõ.

Mô hình phân cấp giúp biểu diễn phần chung và phần riêng một cách có chủ đích:

- **Kiểu cha (supertype):** mô tả khái niệm tổng quát và các thuộc tính/quan hệ chung.
- **Kiểu con (subtype):** mô tả một nhóm đối tượng cụ thể thuộc kiểu cha, có thêm thuộc tính, quan hệ hoặc quy tắc riêng.

Ví dụ:

~~~text
                 WORKER
          (worker_id, full_name)
                    |
          ---------------------
          |                   |
     EMPLOYEE             CONTRACTOR
     (salary_grade)       (contract_end)
~~~

Một Employee cũng là một Worker; một Contractor cũng là một Worker. Cả hai kế thừa định danh và các thuộc tính chung từ Worker theo mô hình khái niệm.

Điểm quan trọng là phân cấp phải phản ánh ý nghĩa nghiệp vụ. Việc một lớp trong code kế thừa lớp khác chưa đủ để kết luận hai khái niệm dữ liệu có quan hệ supertype/subtype.

## 2. Tổng quát hóa và chuyên biệt hóa

Hai hướng tiếp cận này cùng tạo ra một phân cấp nhưng bắt đầu từ hai hướng phân tích khác nhau.

### 2.1. Tổng quát hóa (generalization)

**Tổng quát hóa** là quá trình đi từ nhiều kiểu cụ thể lên một kiểu tổng quát bằng cách tìm phần chung.

Ví dụ, một hệ thống có hai khái niệm:

- Customer cá nhân: customer_id, tên, email, địa chỉ liên hệ.
- Customer doanh nghiệp: customer_id, tên pháp lý, email liên hệ, địa chỉ đăng ký.

Nếu cả hai cùng có định danh khách hàng, thông tin liên hệ và quy tắc quản lý chung, có thể tổng quát hóa thành Customer, rồi chuyên biệt thành IndividualCustomer và BusinessCustomer.

Quá trình này thường theo hướng bottom-up:

1. Nhận diện các kiểu thực thể cụ thể.
2. So sánh thuộc tính, quan hệ và quy tắc.
3. Xác định phần chung thực sự có cùng ý nghĩa.
4. Tạo supertype chứa phần chung.
5. Giữ các thuộc tính và quy tắc riêng ở subtype.

Không nên tổng quát hóa chỉ vì hai bảng có cột cùng tên. Hai trường có tên email có thể có ngữ nghĩa, nguồn chuẩn hoặc quy tắc xác minh khác nhau.

### 2.2. Chuyên biệt hóa (specialization)

**Chuyên biệt hóa** là quá trình bắt đầu từ một kiểu tổng quát rồi chia thành các kiểu con theo những tiêu chí nghiệp vụ có ý nghĩa.

Ví dụ, Payment là khái niệm chung có payment_id, amount, currency và created_at. Có thể chuyên biệt thành:

- CardPayment: có card_token và authorization_code.
- BankTransferPayment: có bank_reference và bank_account.
- CashPayment: có collected_at và collector_id.

Quá trình này thường theo hướng top-down:

1. Xác định supertype và phạm vi đối tượng.
2. Tìm các nhóm có quy tắc hoặc dữ liệu khác nhau.
3. Viết điều kiện xác định một đối tượng thuộc subtype.
4. Xác định các subtype có loại trừ nhau hay có thể đồng thời.
5. Xác định mọi đối tượng cha có bắt buộc thuộc ít nhất một subtype không.
6. Kiểm tra các trường hợp không thuộc subtype nào hoặc thuộc nhiều subtype.

### 2.3. So sánh hai hướng

| Tiêu chí | Tổng quát hóa | Chuyên biệt hóa |
|---|---|---|
| Hướng phân tích | Từ nhiều kiểu cụ thể lên kiểu chung | Từ kiểu chung xuống các kiểu cụ thể |
| Câu hỏi chính | Chúng có điểm chung nào cùng ý nghĩa? | Có những nhóm nào cần quy tắc riêng? |
| Kết quả | Supertype và phần chung | Subtype và tiêu chí thành viên |
| Rủi ro | Gom các khái niệm chỉ giống tên hoặc cấu trúc | Chia quá nhiều subtype hoặc tiêu chí không rõ |

Trong thực tế, hai hướng thường được dùng lặp lại. Khi phân tích subtype, nhóm có thể phát hiện một phần chung mới cần tổng quát hóa; khi tổng quát hóa, nhóm có thể phát hiện những loại đối tượng khác biệt cần chuyên biệt hóa.

## 3. Supertype và subtype có ý nghĩa gì?

### 3.1. Supertype

Supertype đại diện cho khái niệm chung. Nó chứa:

- định danh chung;
- thuộc tính có ý nghĩa với mọi thành viên;
- quan hệ áp dụng cho mọi thành viên;
- bất biến chung;
- các hành vi hoặc sự kiện chung nếu có.

Ví dụ, Payment có thể chứa:

- payment_id;
- order_id;
- amount;
- currency;
- status;
- created_at.

Những thuộc tính này có ý nghĩa với mọi phương thức thanh toán trong phạm vi mô hình.

### 3.2. Subtype

Subtype đại diện cho một tập con của supertype. Một đối tượng thuộc subtype đồng thời là một đối tượng thuộc supertype.

Ví dụ, CardPayment là một Payment. Nó có thể bổ sung:

- payment_token;
- authorization_code;
- card_network.

Các thuộc tính riêng này chỉ có ý nghĩa đối với thanh toán bằng thẻ.

Một subtype thường:

- kế thừa định danh của supertype;
- kế thừa thuộc tính và quan hệ chung;
- bổ sung thuộc tính hoặc quan hệ riêng;
- chịu các bất biến chung và các bất biến đặc thù.

### 3.3. Quan hệ is-a

Quan hệ giữa subtype và supertype là quan hệ **is-a**:

- CardPayment is a Payment.
- BusinessCustomer is a Customer.
- FullTimeEmployee is a Worker.

Nếu không thể nói câu is-a một cách tự nhiên và đúng nghiệp vụ, có thể đang mô hình hóa nhầm quan hệ has-a, role hoặc category thành kế thừa.

Ví dụ:

- Car has an Engine: đây là quan hệ thành phần, không phải Car là một Engine.
- Employee has a Department: đây là quan hệ tham chiếu, không phải Employee là Department.
- Customer has a PreferredLanguage: đây thường là thuộc tính, không phải subtype.

### 3.4. Subtype kế thừa định danh, không tạo một đối tượng độc lập khác

Một CardPayment không phải một Payment riêng cộng thêm một CardPayment khác. Nó là cùng một thực thể được nhìn ở mức tổng quát và mức chuyên biệt.

Trong mô hình quan hệ, cách triển khai có thể dùng nhiều bảng, nhưng các hàng ở bảng subtype phải gắn với cùng định danh của hàng supertype. Không nên tạo hai ID độc lập nếu nghiệp vụ xem đó là một đối tượng duy nhất.

## 4. Tiêu chí chia kiểu con phải rõ ràng

Một subtype cần có tiêu chí thành viên có thể giải thích và kiểm chứng. Tiêu chí đó xác định đối tượng nào thuộc nhóm và khi nào tư cách thành viên thay đổi.

### 4.1. Tiêu chí dựa trên loại nghiệp vụ

Ví dụ, Customer được phân thành IndividualCustomer và BusinessCustomer dựa trên tư cách pháp lý của bên mua.

- IndividualCustomer là khách hàng cá nhân.
- BusinessCustomer là khách hàng là tổ chức/doanh nghiệp.

Tiêu chí này có ý nghĩa vì hai nhóm có thể có thông tin pháp lý, quy trình xác minh và nghĩa vụ hóa đơn khác nhau.

### 4.2. Tiêu chí dựa trên quy tắc hoặc chính sách

Ví dụ, Worker được phân thành Employee và Contractor dựa trên loại quan hệ lao động đã được tổ chức xác nhận.

Điều kiện có thể gồm:

- Employee có quan hệ lao động theo hợp đồng nhân viên.
- Contractor cung cấp dịch vụ theo hợp đồng nhà thầu.

Không nên dùng một thuộc tính không ổn định như email công ty hoặc tên phòng ban làm tiêu chí nếu nó không xác định đúng loại quan hệ.

### 4.3. Tiêu chí dựa trên khả năng hoặc cấu trúc riêng

Ví dụ, phương thức thanh toán có thể chia theo cách xử lý:

- CardPayment cần token và authorization.
- BankTransferPayment cần mã tham chiếu ngân hàng.
- CashPayment cần người thu và thời điểm thu.

Khác biệt phải có ý nghĩa về dữ liệu, quy trình hoặc bất biến. Nếu các loại chỉ khác nhãn hiển thị nhưng không có thuộc tính hay quy tắc riêng, một thuộc tính loại có thể đủ.

### 4.4. Viết predicate cho subtype

Tiêu chí subtype nên được viết thành điều kiện logic hoặc câu nghiệp vụ rõ:

~~~text
CardPayment(p) :=
    p.method = 'CARD'
    AND p.authorization_required = true
~~~

Hoặc:

> Một Worker thuộc Employee khi hồ sơ có quan hệ lao động nhân viên đã được phê duyệt và đang có hiệu lực.

Predicate giúp trả lời:

- Dữ liệu nào chứng minh thành viên subtype?
- Có thể kiểm tra tự động không?
- Ai có quyền xác nhận?
- Điều kiện có thể thay đổi theo thời gian không?
- Một đối tượng có thể đồng thời thỏa nhiều predicate không?

Không nhất thiết predicate phải là biểu thức SQL. Nó là định nghĩa nghiệp vụ, sau đó mới chọn cách lưu và thực thi.

### 4.5. Không chia subtype theo màn hình hoặc quyền truy cập đơn thuần

Những lý do sau thường chưa đủ để tạo subtype:

- màn hình A hiển thị ít trường hơn màn hình B;
- nhóm người dùng có quyền xem khác nhau;
- một báo cáo cần một tập cột riêng;
- một quy trình chỉ xử lý một số bản ghi;
- API có hai cách serialize.

Các khác biệt đó có thể được giải quyết bằng view, projection, policy, role hoặc API DTO. Chỉ tạo subtype khi có khác biệt về khái niệm, thuộc tính, quan hệ hoặc bất biến nghiệp vụ.

## 5. Hai trục ràng buộc của phân cấp

Khi chia một supertype thành nhiều subtype, cần trả lời hai câu hỏi độc lập:

1. Một đối tượng có thể thuộc nhiều subtype cùng lúc không?
2. Mọi đối tượng thuộc supertype có bắt buộc thuộc ít nhất một subtype không?

Câu hỏi thứ nhất xác định **disjointness**. Câu hỏi thứ hai xác định **completeness**.

### 5.1. Disjoint subtype

Phân cấp **disjoint** nghĩa là một đối tượng supertype chỉ có thể thuộc tối đa một subtype trong nhóm được xét.

Ví dụ, nếu chính sách quy định mỗi Payment chỉ dùng đúng một phương thức xử lý chính, CardPayment và BankTransferPayment có thể disjoint.

~~~text
                PAYMENT
                   |
                {disjoint}
                /       \
       CARD_PAYMENT   BANK_TRANSFER
~~~

Một Payment không thể đồng thời là CardPayment và BankTransferPayment theo mô hình này.

### 5.2. Overlapping subtype

Phân cấp **overlapping** cho phép một đối tượng thuộc nhiều subtype cùng lúc.

Ví dụ, một người có thể vừa là Customer vừa là Supplier của cùng một nền tảng. Nếu supertype là Party, các subtype Customer và Supplier có thể overlapping.

~~~text
                  PARTY
                    |
                {overlap}
                /       \
           CUSTOMER   SUPPLIER
~~~

Không nên ép hai vai trò này thành một loại duy nhất nếu một tổ chức có thể đồng thời mua và cung cấp hàng hóa.

### 5.3. Total specialization

Phân cấp **total** nghĩa là mọi đối tượng của supertype phải thuộc ít nhất một subtype trong tập subtype đã định nghĩa.

Ví dụ, nếu hệ thống chỉ ghi nhận Payment sau khi phương thức đã được chọn và mọi phương thức hợp lệ đều thuộc CardPayment, BankTransferPayment hoặc CashPayment, phân cấp có thể total.

### 5.4. Partial specialization

Phân cấp **partial** cho phép đối tượng supertype chưa thuộc subtype nào trong nhóm được xét.

Ví dụ, một Payment có thể được tạo ở trạng thái PENDING_METHOD trước khi khách chọn phương thức. Khi đó Payment chưa thuộc CardPayment, BankTransferPayment hay CashPayment.

### 5.5. Bốn tổ hợp

Disjointness và completeness là hai trục độc lập:

| | Total | Partial |
|---|---|---|
| Disjoint | Mỗi đối tượng thuộc đúng một subtype | Mỗi đối tượng thuộc tối đa một subtype, có thể chưa thuộc subtype nào |
| Overlapping | Mỗi đối tượng thuộc ít nhất một subtype, có thể thuộc nhiều subtype | Có thể thuộc không, một hoặc nhiều subtype |

Cần xác định rõ tổ hợp được chọn cho từng phân cấp. Không nên mặc định mọi hệ phân cấp đều disjoint và total.

## 6. Phân cấp có thể thay đổi theo thời gian

Một đối tượng có thể chuyển từ subtype này sang subtype khác hoặc bắt đầu/kết thúc một vai trò.

Ví dụ:

- Contractor trở thành Employee.
- Khách hàng cá nhân chuyển thành khách hàng doanh nghiệp sau khi thay đổi chủ thể ký hợp đồng.
- Một Party bắt đầu hoặc kết thúc vai trò Supplier.
- Một Payment chuyển từ PENDING_METHOD sang loại phương thức cụ thể sau khi người dùng chọn.

Cần hỏi:

- Việc đổi subtype có thay đổi danh tính đối tượng không?
- Có phải giữ lịch sử loại cũ không?
- Thuộc tính riêng của subtype cũ xử lý thế nào?
- Quan hệ phụ thuộc subtype có cần chuyển đổi không?
- Có khoảng thời gian hai subtype cùng hiệu lực không?

### 6.1. Thay đổi subtype nhưng giữ định danh

Nếu vẫn là cùng một thực thể nghiệp vụ, thường giữ ID supertype. Việc chuyển subtype là thay đổi phân loại hoặc vai trò, không phải tạo một người/đối tượng mới.

Ví dụ, Worker vẫn giữ worker_id khi chuyển từ Contractor sang Employee. Hợp đồng nhà thầu cũ được đóng; hồ sơ quan hệ lao động mới được mở.

### 6.2. Lưu lịch sử thành viên subtype

Nếu cần audit, có thể lưu lịch sử phân loại:

~~~text
WORKER_TYPE_HISTORY
- worker_id
- worker_type
- valid_from
- valid_to
- recorded_at
~~~

Cần quy định khoảng thời gian có bao gồm đầu/cuối hay không, và các khoảng có được chồng lấn hay không. Nếu chỉ lưu subtype hiện tại, không thể trả lời loại quan hệ của Worker tại một thời điểm trong quá khứ.

### 6.3. Phân biệt subtype với role

Role thường có thể được thêm hoặc gỡ mà không thay đổi loại cơ bản của thực thể.

Ví dụ, Party có thể đồng thời đóng vai trò Customer và Supplier. Đây là vai trò nghiệp vụ có thể thay đổi độc lập. Tùy miền, có thể mô hình hóa role bằng bảng liên kết có hiệu lực theo thời gian thay vì kế thừa cứng.

Subtype thường mô tả một loại chuyên biệt của khái niệm; role mô tả tư cách mà một thực thể đảm nhiệm trong một ngữ cảnh hoặc khoảng thời gian. Ranh giới cần dựa vào ngôn ngữ nghiệp vụ và vòng đời thực tế.

## 7. Biểu diễn phân cấp trong ERD

Một sơ đồ phân cấp thường thể hiện supertype và các subtype cùng quan hệ kế thừa.

Ví dụ:

~~~mermaid
classDiagram
    class PAYMENT {
      +payment_id
      +amount
      +currency
      +status
    }
    class CARD_PAYMENT {
      +payment_token
      +authorization_code
    }
    class BANK_TRANSFER_PAYMENT {
      +bank_reference
      +bank_account
    }
    PAYMENT <|-- CARD_PAYMENT
    PAYMENT <|-- BANK_TRANSFER_PAYMENT
~~~

Sơ đồ cho thấy subtype kế thừa khái niệm chung từ PAYMENT và bổ sung dữ liệu riêng. Tuy nhiên, sơ đồ lớp đơn giản chưa thể hiện đầy đủ disjointness, overlap, total hay partial. Cần thêm ký hiệu, ghi chú hoặc constraint trong tài liệu mô hình.

### 7.1. Phân biệt kế thừa với quan hệ thông thường

Một đường kế thừa biểu diễn is-a. Một đường association biểu diễn liên kết giữa các thực thể.

Ví dụ:

- CardPayment is a Payment: kế thừa.
- Payment belongs to Order: quan hệ tham chiếu.
- Payment uses PaymentProvider: quan hệ tham chiếu hoặc hợp tác.
- Payment has PaymentAttempt: quan hệ thành phần hoặc liên kết theo vòng đời.

Không nên vẽ mọi đường nối thành kế thừa. Mỗi loại quan hệ có ý nghĩa và cách triển khai khác nhau.

### 7.2. Ký hiệu phân cấp

Một số ký pháp ERD dùng vòng tròn chuyên biệt hóa với nhãn:

- d: disjoint;
- o: overlapping;
- đường đơn hoặc đôi để biểu thị partial/total tùy ký pháp.

Quy ước khác nhau giữa công cụ. Hãy ghi legend rõ ràng và không dựa vào hình vẽ nếu chưa xác nhận ý nghĩa của công cụ đang dùng.

## 8. Ánh xạ phân cấp sang cơ sở dữ liệu quan hệ

Mô hình khái niệm supertype/subtype có thể được triển khai theo nhiều chiến lược. Không có một chiến lược tốt nhất cho mọi trường hợp.

### 8.1. Một bảng cho toàn bộ phân cấp (single table / table-per-hierarchy)

Tất cả thuộc tính chung và riêng được lưu trong một bảng, dùng cột discriminator để xác định subtype.

~~~sql
CREATE TABLE payments (
    payment_id BIGINT PRIMARY KEY,
    payment_type VARCHAR(30) NOT NULL,
    amount NUMERIC(12, 2) NOT NULL CHECK (amount > 0),
    currency CHAR(3) NOT NULL,
    card_token VARCHAR(200),
    authorization_code VARCHAR(100),
    bank_reference VARCHAR(100),
    cash_collector_id BIGINT,
    cash_collected_at TIMESTAMP,
    CHECK (
        (payment_type = 'CARD'
            AND card_token IS NOT NULL
            AND bank_reference IS NULL
            AND cash_collector_id IS NULL)
        OR
        (payment_type = 'BANK_TRANSFER'
            AND bank_reference IS NOT NULL
            AND card_token IS NULL
            AND cash_collector_id IS NULL)
        OR
        (payment_type = 'CASH'
            AND cash_collector_id IS NOT NULL
            AND cash_collected_at IS NOT NULL
            AND card_token IS NULL
            AND bank_reference IS NULL)
    )
);
~~~

Ưu điểm:

- truy vấn supertype đơn giản vì dữ liệu ở một bảng;
- không cần JOIN để đọc thuộc tính chung và riêng;
- insert/update một đối tượng thường đơn giản.

Hạn chế:

- nhiều cột subtype có thể NULL;
- schema phình khi có nhiều subtype;
- CHECK phức tạp khi có nhiều loại;
- overlapping subtype khó biểu diễn bằng một discriminator đơn;
- thay đổi subtype có thể cần cập nhật nhiều cột và quy tắc.

Chiến lược này phù hợp khi số subtype ít, cấu trúc tương đối ổn định và các truy vấn thường cần đọc toàn bộ phân cấp.

### 8.2. Bảng cho supertype và từng subtype (class/table-per-type)

Thuộc tính chung lưu ở bảng cha; mỗi subtype có bảng riêng, dùng cùng khóa làm PK và FK.

~~~sql
CREATE TABLE payments (
    payment_id BIGINT PRIMARY KEY,
    amount NUMERIC(12, 2) NOT NULL CHECK (amount > 0),
    currency CHAR(3) NOT NULL,
    status VARCHAR(20) NOT NULL
);

CREATE TABLE card_payments (
    payment_id BIGINT PRIMARY KEY
        REFERENCES payments(payment_id),
    card_token VARCHAR(200) NOT NULL,
    authorization_code VARCHAR(100)
);

CREATE TABLE bank_transfer_payments (
    payment_id BIGINT PRIMARY KEY
        REFERENCES payments(payment_id),
    bank_reference VARCHAR(100) NOT NULL
);

CREATE TABLE cash_payments (
    payment_id BIGINT PRIMARY KEY
        REFERENCES payments(payment_id),
    collector_id BIGINT NOT NULL,
    collected_at TIMESTAMP NOT NULL
);
~~~

Ưu điểm:

- thuộc tính riêng nằm ở bảng phù hợp;
- giảm cột NULL trong bảng cha;
- ràng buộc theo subtype rõ hơn;
- có thể mở rộng subtype mà ít ảnh hưởng các subtype khác.

Hạn chế:

- đọc một đối tượng subtype cần JOIN;
- insert/delete cần thao tác nhiều bảng trong cùng transaction;
- FK đến supertype không tự bảo đảm disjoint hoặc total;
- truy vấn tất cả Payment cần JOIN/UNION tùy nhu cầu.

Đây thường là cách biểu diễn trực tiếp, rõ ràng khi subtype có nhiều thuộc tính hoặc quy tắc riêng.

### 8.3. Bảng riêng cho từng kiểu cụ thể (table-per-concrete-type)

Mỗi subtype có bảng chứa cả thuộc tính chung và thuộc tính riêng. Không có bảng supertype vật lý riêng.

~~~sql
CREATE TABLE card_payments (
    payment_id BIGINT PRIMARY KEY,
    amount NUMERIC(12, 2) NOT NULL,
    currency CHAR(3) NOT NULL,
    status VARCHAR(20) NOT NULL,
    card_token VARCHAR(200) NOT NULL
);

CREATE TABLE bank_transfer_payments (
    payment_id BIGINT PRIMARY KEY,
    amount NUMERIC(12, 2) NOT NULL,
    currency CHAR(3) NOT NULL,
    status VARCHAR(20) NOT NULL,
    bank_reference VARCHAR(100) NOT NULL
);
~~~

Ưu điểm:

- mỗi subtype có bảng độc lập;
- truy vấn một loại cụ thể không cần JOIN bảng cha;
- thuộc tính riêng và chung nằm cùng hàng.

Hạn chế:

- thuộc tính chung bị lặp giữa các bảng;
- cập nhật quy tắc chung phải đồng bộ nhiều bảng;
- khóa duy nhất toàn phân cấp khó bảo đảm nếu không có bảng/registry chung;
- truy vấn toàn bộ Payment cần UNION;
- quan hệ tham chiếu đến Payment chung trở nên khó biểu diễn bằng một FK đơn giản.

Chiến lược này có thể phù hợp khi subtype được lưu và truy vấn độc lập, nhưng cần đánh giá kỹ việc lặp dữ liệu và định danh chung.

### 8.4. So sánh ba chiến lược

| Chiến lược | Lưu thuộc tính chung | Lưu thuộc tính riêng | Điểm mạnh | Hạn chế chính |
|---|---|---|---|---|
| Single table | Một bảng | Cùng bảng | Đọc đơn giản, ít JOIN | Nhiều cột NULL, constraint phức tạp |
| Table-per-type | Bảng cha | Bảng từng subtype | Cấu trúc rõ, chuẩn hóa tốt | JOIN và transaction nhiều bảng |
| Table-per-concrete-type | Lặp ở mỗi bảng con | Cùng bảng con | Truy vấn subtype riêng đơn giản | Lặp thuộc tính chung, khó tham chiếu toàn cục |

### 8.5. Chọn chiến lược theo workload và quy tắc

Hãy xét:

- số lượng subtype hiện tại và dự kiến;
- thuộc tính riêng có nhiều hay ít;
- truy vấn thường đọc supertype hay một subtype cụ thể;
- subtype có disjoint hay overlapping;
- có yêu cầu FK tham chiếu đến mọi loại đối tượng không;
- cần enforce total/disjoint ở database đến mức nào;
- việc thêm subtype mới có thường xuyên không;
- có cần lịch sử chuyển subtype không.

Đừng chọn chỉ dựa trên số lượng bảng ít nhất. Hãy xem cách biểu diễn bảo vệ được quy tắc và hỗ trợ các truy vấn quan trọng.

## 9. Discriminator và kiểm soát thành viên subtype

Discriminator là thuộc tính dùng để chỉ ra subtype của một bản ghi, thường gặp trong table-per-hierarchy.

Ví dụ:

~~~text
payment_type = CARD
payment_type = BANK_TRANSFER
payment_type = CASH
~~~

Discriminator có thể là enum, mã loại hoặc thuộc tính có ý nghĩa nghiệp vụ. Nó phải có định nghĩa và tập giá trị được kiểm soát.

### 9.1. Disjoint

Nếu các subtype disjoint, một discriminator đơn thường phù hợp vì mỗi bản ghi chỉ có một loại. CHECK có thể bảo đảm các cột riêng phù hợp với loại được chọn.

### 9.2. Overlapping

Nếu một đối tượng có thể thuộc nhiều subtype, một discriminator đơn thường không đủ. Có thể cần:

- nhiều cờ thành viên;
- bảng subtype riêng với cùng supertype ID;
- bảng membership/role;
- hoặc mô hình thành phần khác phù hợp với ngữ nghĩa.

Ví dụ, Party vừa là Customer vừa là Supplier không nên ép vào một cột party_type duy nhất nếu hai vai trò có thể cùng tồn tại.

### 9.3. Total

Nếu specialization total, cần bảo đảm mỗi supertype thuộc ít nhất một subtype. FK từ bảng subtype lên bảng cha chỉ bảo đảm subtype có cha; nó không bảo đảm mọi cha có subtype.

Có thể bảo vệ bằng discriminator NOT NULL trong single-table, trigger/constraint phù hợp hoặc quy trình transaction. Với table-per-type, kiểm tra total thường phức tạp hơn và phụ thuộc khả năng hệ quản trị.

### 9.4. Disjoint

Nếu subtype disjoint, cần ngăn một supertype ID xuất hiện trong nhiều bảng subtype cùng lúc. Một bảng subtype riêng với PK payment_id trong mỗi bảng không tự ngăn cùng ID xuất hiện ở hai bảng khác nhau.

Có thể dùng discriminator ở bảng cha, trigger hoặc một mô hình đăng ký subtype để kiểm soát. Cần chọn cách phù hợp với công nghệ và kiểm thử cập nhật đồng thời.

## 10. Quan hệ tham chiếu đến supertype hay subtype?

Khi một thực thể khác cần tham chiếu phân cấp, hãy xác định nó cần mọi loại hay chỉ một subtype cụ thể.

### 10.1. Tham chiếu supertype

Ví dụ, một Order có thể có nhiều Payment bất kể phương thức thanh toán:

~~~text
ORDER -> PAYMENT
           |
       -------------
       |           |
   CARD_PAYMENT  BANK_TRANSFER
~~~

Order nên tham chiếu Payment supertype vì quan hệ áp dụng cho mọi phương thức.

### 10.2. Tham chiếu subtype

Nếu một thực thể chỉ có thể tham chiếu CardPayment, quan hệ có thể trỏ trực tiếp đến subtype hoặc dùng một FK đến supertype kèm quy tắc xác minh subtype.

Ví dụ, bảng CardAuthorization chỉ liên quan đến CardPayment. Trong mô hình quan hệ table-per-type, nó có thể tham chiếu card_payments(payment_id).

### 10.3. Tránh FK polymorphic không được bảo vệ

Một thiết kế như:

~~~text
target_type
target_id
~~~

có thể cho phép một hàng tham chiếu đến nhiều bảng khác nhau tùy target_type. Nhưng FK thông thường không thể tự bảo đảm target_id tồn tại trong bảng được chọn bởi giá trị target_type.

Nếu dùng polymorphic reference, cần cơ chế kiểm soát rõ như bảng supertype chung, trigger hoặc thiết kế liên kết riêng. Nếu không, dữ liệu mồ côi có thể xuất hiện.

## 11. Khi nào không nên tạo subtype?

Không phải mọi khác biệt đều cần phân cấp.

### 11.1. Chỉ khác một vài thuộc tính tùy chọn

Nếu một loại khách hàng chỉ có thêm một trường ít dùng, có thể dùng thuộc tính nullable hoặc bảng mở rộng nếu có lý do rõ. Không nhất thiết phải tạo subtype.

Tuy nhiên, nếu trường đó đi kèm quy tắc xác minh, vòng đời hoặc quan hệ riêng, subtype có thể giúp mô hình rõ hơn.

### 11.2. Chỉ khác trạng thái

Trạng thái như ACTIVE, SUSPENDED, CLOSED thường là các trạng thái của cùng một thực thể, không phải subtype.

Ví dụ, tài khoản đang hoạt động và tài khoản bị khóa vẫn là cùng loại Account. Chuyển trạng thái không tạo ra một loại tài khoản mới trừ khi nghiệp vụ định nghĩa cấu trúc và quy tắc khác biệt thực sự.

### 11.3. Chỉ khác vai trò

Một tổ chức có thể vừa là khách hàng vừa là nhà cung cấp. Nếu hai vai trò có thể đồng thời tồn tại và thay đổi độc lập, mô hình role/membership thường phù hợp hơn một phân cấp disjoint.

### 11.4. Chỉ khác quyền truy cập

Quyền xem/sửa dữ liệu nên được mô hình hóa bằng authorization, role và policy. Không nên tạo subtype chỉ để nhóm người dùng nhìn thấy tập trường khác nhau.

### 11.5. Chỉ khác định dạng đầu ra

API DTO, view hoặc projection có thể cung cấp cấu trúc khác nhau cho từng client. Điều đó không nhất thiết làm thay đổi mô hình dữ liệu khái niệm.

## 12. Kiểm chứng phân cấp bằng tình huống

Trước khi chốt, hãy kiểm tra các trường hợp:

1. Một đối tượng chỉ thuộc một subtype.
2. Một đối tượng thuộc đồng thời hai subtype.
3. Một đối tượng chưa thuộc subtype nào.
4. Một đối tượng không thỏa bất kỳ predicate subtype nào.
5. Một đối tượng thay đổi từ subtype A sang subtype B.
6. Một subtype mới được thêm vào.
7. Một quan hệ tham chiếu supertype cần truy xuất mọi loại.
8. Một quan hệ chỉ được phép tham chiếu một subtype cụ thể.
9. Hai transaction đồng thời thay đổi thành viên subtype.
10. Dữ liệu cũ không có discriminator hoặc có giá trị loại không còn hợp lệ.

Với mỗi tình huống, kiểm tra:

- predicate thành viên có rõ không;
- disjoint/overlap có được bảo vệ không;
- total/partial có đúng không;
- định danh có giữ ổn định không;
- thuộc tính subtype có bị bỏ sót hoặc để lại dữ liệu mồ côi không;
- các FK và quan hệ phụ thuộc có hợp lệ không;
- lịch sử chuyển loại có được lưu nếu cần không.

### 12.1. Tiêu chí chấp nhận minh họa

Với Payment được chia thành CardPayment và BankTransferPayment, giả sử hai subtype disjoint và specialization total sau khi Payment được xác nhận:

- Mỗi Payment CONFIRMED phải thuộc đúng một trong hai subtype.
- CardPayment phải có card_token hợp lệ.
- BankTransferPayment phải có bank_reference.
- Một payment_id không được xuất hiện đồng thời trong cả hai bảng subtype.
- Payment ở trạng thái PENDING_METHOD có thể chưa thuộc subtype nào.
- Khi phương thức đã được xác nhận, không được đổi subtype nếu không đi qua quy trình nghiệp vụ được phép.
- Mọi subtype record phải tham chiếu một Payment tồn tại.

Các tiêu chí này vừa xác định hành vi, vừa chỉ ra constraint và test cần có.

## 13. Những sai lầm thường gặp

- **Tạo subtype chỉ vì bảng có cột khác nhau:** khác biệt cấu trúc chưa đủ; cần tiêu chí nghiệp vụ và quy tắc riêng.
- **Nhầm is-a với has-a:** quan hệ thành phần hoặc tham chiếu không phải kế thừa.
- **Không viết predicate subtype:** người nhập dữ liệu không biết khi nào đối tượng thuộc kiểu con.
- **Mặc định disjoint và total:** thực tế có thể overlapping hoặc partial.
- **Dùng một discriminator cho subtype overlapping:** một đối tượng có thể thuộc nhiều nhóm nên một giá trị đơn không diễn tả đủ.
- **Cho rằng FK subtype bảo đảm total:** FK chỉ bảo đảm bản ghi con có cha, không buộc mọi cha có bản ghi con.
- **Cho rằng PK riêng trong từng bảng subtype bảo đảm disjoint:** cùng ID vẫn có thể xuất hiện ở nhiều bảng con khác nhau.
- **Coi trạng thái hoặc role là subtype:** làm phân cấp cứng và khó thay đổi khi vai trò đồng thời hoặc thay đổi theo thời gian.
- **Không xét lịch sử chuyển loại:** báo cáo quá khứ có thể diễn giải sai loại đối tượng tại thời điểm đó.
- **Chọn chiến lược bảng chỉ theo số lượng JOIN:** cần cân bằng constraint, truy vấn, tính mở rộng và tính toàn vẹn.
- **Dùng target_type/target_id mà không bảo vệ tham chiếu:** có thể tạo liên kết mồ côi.
- **Không kiểm thử subtype mới:** thêm một loại có thể phá vỡ giả định total/disjoint và các đoạn code xử lý discriminator.

## 14. Kết luận

Tổng quát hóa tìm phần chung giữa các kiểu cụ thể để tạo supertype; chuyên biệt hóa chia một supertype thành các subtype dựa trên tiêu chí nghiệp vụ. Mỗi subtype phải là một trường hợp is-a, kế thừa định danh và quy tắc chung, đồng thời có thuộc tính hoặc bất biến riêng đủ ý nghĩa.

Khi thiết kế phân cấp, hãy viết predicate thành viên, xác định disjoint hay overlapping và total hay partial, xem xét vòng đời cùng lịch sử thay đổi, rồi chọn chiến lược ánh xạ phù hợp với workload và khả năng bảo vệ constraint. Một phân cấp tốt giúp biểu diễn đúng khái niệm và quy tắc, tránh lặp dữ liệu và vẫn có thể tiến hóa khi nghiệp vụ thay đổi.

## Tự kiểm tra

1. Phân biệt tổng quát hóa và chuyên biệt hóa bằng một ví dụ.
2. Vì sao subtype phải thỏa quan hệ is-a với supertype?
3. Disjoint/overlapping khác total/partial như thế nào?
4. Một Party có thể vừa là Customer vừa là Supplier. Nên chọn phân cấp overlapping hay mô hình role? Giải thích.
5. Vì sao FK từ bảng subtype đến bảng supertype không tự bảo đảm specialization total?
6. So sánh single table, table-per-type và table-per-concrete-type.
7. Khi nào trạng thái hoặc quyền truy cập không nên được mô hình hóa thành subtype?
8. Nếu một Contractor trở thành Employee, cần xem xét định danh, thuộc tính và lịch sử nào?
9. Một hệ thống có Payment, CardPayment và BankTransferPayment. Hãy viết predicate, completeness/disjointness và đề xuất schema để bảo vệ các quy tắc đó.

