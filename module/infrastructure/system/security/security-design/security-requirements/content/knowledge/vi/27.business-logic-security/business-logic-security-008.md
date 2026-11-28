# Transaction integrity — Đặc tả tính toàn vẹn của giao dịch nghiệp vụ

## 1. Toàn vẹn giao dịch cần bảo vệ điều gì?

Transaction integrity là khả năng bảo đảm một giao dịch tạo ra đúng thay đổi đã được cho phép, với dữ liệu và điều kiện hợp lệ, không bị thực hiện thiếu, thừa, sửa nội dung hoặc lặp ngoài chủ đích.

Một giao dịch nghiệp vụ có thể bao gồm nhiều thao tác kỹ thuật: ghi đơn hàng, giữ tồn kho, ghi nhận thanh toán, cập nhật số dư, tạo sự kiện và gửi thông báo. Tính toàn vẹn cần được đánh giá trên toàn bộ kết quả nghiệp vụ, không chỉ trên một câu lệnh SQL.

Trong module `SECURITY_SECURITY_DESIGN_SECURITY_REQUIREMENTS`, mục tiêu là chuyển các rủi ro như sửa số tiền, chi lặp, ghi nhận một phần hoặc mất giao dịch đã xác nhận thành yêu cầu đo được và có thể kiểm chứng.

Một yêu cầu đầy đủ cần làm rõ:

- Ai được thực hiện giao dịch và trên những tài nguyên nào?
- Nội dung nào đã được kiểm tra, xác nhận hoặc phê duyệt?
- Bất biến dữ liệu nào phải đúng sau mỗi kết quả được chấp nhận?
- Những thay đổi nào phải cùng thành công hoặc cùng không có hiệu lực?
- Cạnh tranh, retry, timeout và khởi động lại được xử lý thế nào?
- Khi giao dịch trải qua nhiều hệ thống, trạng thái chưa rõ được đối soát ra sao?
- Dữ liệu và bằng chứng nào chứng minh kết quả thực tế khớp quyết định được phép?

Các giá trị số trong bài chỉ phục vụ ví dụ thiết kế và nghiệm thu. Chúng không phải ngưỡng bắt buộc cho mọi sản phẩm.

## 2. Phân biệt các lớp toàn vẹn

| Lớp | Mục tiêu | Điều chưa tự được bảo đảm |
| --- | --- | --- |
| Toàn vẹn truyền dữ liệu | Nội dung không bị sửa ngoài ý muốn trên đường truyền theo cơ chế bảo vệ | Số tiền client gửi có thể vẫn sai về nghiệp vụ |
| Kiểm tra đầu vào | Kiểu, miền giá trị và cấu trúc hợp lệ | Người gửi có được thực hiện giao dịch đó không |
| Xác thực và phân quyền | Đúng chủ thể, đúng quyền với thao tác và đối tượng | Nội dung có còn khớp bản đã xác nhận không |
| Kiểm chứng trạng thái | Thao tác phù hợp với trạng thái hiện hành | Các thay đổi nhiều bản ghi có cùng commit không |
| Transaction của kho dữ liệu | Cung cấp đặc tính nhất quán, cô lập và bền vững theo cơ chế cấu hình | Ứng dụng đã mô hình hóa đúng bất biến và phụ thuộc ngoài chưa |
| Toàn vẹn nghiệp vụ đầu cuối | Kết quả thực tế khớp giao dịch được phép, không thiếu/thừa/lặp | Cần phối hợp tất cả các lớp trên |

Một bản ghi có chữ ký hoặc checksum đúng vẫn có thể mô tả việc chuyển tiền sai người nhận. Một transaction DB commit thành công vẫn có thể commit giá do client tự chọn nếu ứng dụng tin sai nguồn dữ liệu.

Do đó, toàn vẹn giao dịch bao gồm cả **tính đúng của quyết định**, **tính đúng của thay đổi** và **khả năng kiểm chứng kết quả**.

## 3. Ví dụ xuyên suốt: chuyển giá trị nội bộ

Xét dịch vụ chuyển giá trị giữa các tài khoản trong cùng tenant và cùng đồng tiền. Trong ví dụ ban đầu, tài khoản, số dư phục vụ quyết định và sổ giao dịch nằm trong cùng một ranh giới transaction của kho dữ liệu có thẩm quyền.

Giả định:

- Không cho phép số dư khả dụng âm.
- Máy chủ xác định nguồn, đích, số tiền, phí và quy tắc được áp dụng.
- Người dùng phải có quyền sử dụng tài khoản nguồn.
- Tài khoản nhận và tài khoản thu phí phải hợp lệ.
- Nội dung được xác nhận không được thay đổi trước khi thực hiện.
- Một lệnh chuyển logic không được tạo nhiều lần hạch toán ngoài chính sách.

Ví dụ số liệu theo đơn vị nhỏ nhất được ứng dụng quy định:

| Tài khoản | Trước giao dịch | Thay đổi | Sau giao dịch |
| --- | --- | --- | --- |
| Nguồn | 50.000 | -10.100 | 39.900 |
| Nhận | 7.000 | +10.000 | 17.000 |
| Thu phí | 300 | +100 | 400 |
| Tổng | 57.300 | 0 | 57.300 |

Đây là ví dụ chuyển nội bộ có phí được ghi nhận trong cùng hệ thống. Các sản phẩm khác có thể có cấu trúc sổ khác, nhưng phải xác định rõ các bên được ghi nhận và bất biến tương ứng.

### 3.1. Các bất biến cốt lõi

```text
Tổng các bút toán của giao dịch theo cùng đồng tiền = 0.

Tổng ghi nợ nguồn = số tiền chuyển + phí được phép.

Không tài khoản nào bị ghi nợ ngoài phạm vi đã được cho phép.

Số dư khả dụng không âm nếu chính sách không cho phép thấu chi.

Một giao dịch logic không được có nhiều kết quả hạch toán trái chính sách.

Kết quả SUCCESS chỉ được trả khi điều kiện commit và độ bền được yêu cầu đã đạt.
```

Tổng bằng không chưa chứng minh giao dịch đúng. Một giao dịch chuyển đủ số tiền nhưng sang nhầm tài khoản vẫn cân bằng. Vì vậy cần kiểm tra cả số liệu, danh tính đối tượng, nội dung được phép và quan hệ giữa các bản ghi.

### 3.2. Phạm vi mở rộng

Khi gọi cổng thanh toán ngoài hoặc chuyển sang hệ thống khác, không thể mặc định transaction DB cục bộ bao phủ cả bên ngoài. Phần mở rộng này cần định danh ổn định, trạng thái chờ, đối soát và cơ chế xử lý tác dụng phụ riêng.

Bài học sẽ tách rõ bảo đảm trong một kho dữ liệu với bảo đảm của giao dịch nghiệp vụ nhiều hệ thống.

## 4. Từ mô hình đe dọa đến yêu cầu

| Kịch bản | Vi phạm có thể xảy ra | Hướng yêu cầu |
| --- | --- | --- |
| Client sửa số tiền, phí hoặc người nhận | Thực hiện khác nội dung được phép | Máy chủ tính lại và ràng buộc xác nhận với snapshot giao dịch |
| Người dùng thay ID tài khoản nguồn | Ghi nợ tài sản không thuộc quyền | Phân quyền theo đối tượng, tenant và quyền hiện hành |
| Hai lệnh cùng đọc số dư cũ | Chi vượt khả dụng | Kiểm tra và giữ/ghi nợ bằng cơ chế cạnh tranh phù hợp |
| Lỗi giữa ghi nợ và ghi có | Kết quả một phần | Các thay đổi bắt buộc phải cùng commit |
| Timeout rồi gửi lại | Hạch toán hoặc thanh toán hai lần | Idempotency và chống lặp theo định danh nghiệp vụ |
| Mất phản hồi sau commit | Client tưởng thất bại và tạo lệnh khác | Trạng thái truy vấn được và hợp đồng retry rõ ràng |
| Cập nhật DB xong nhưng chưa gửi sự kiện | Hệ thống sau không nhận được giao dịch | Ghi ý định phát sự kiện bền vững cùng commit khi cần |
| Bên ngoài đã xử lý nhưng nội bộ chưa biết | Gửi lại gây tác dụng phụ lặp | Trạng thái chưa rõ và đối soát theo cùng định danh |
| Sửa lịch sử để che sai lệch | Mất khả năng truy vết | Quyền sửa hạn chế, lưu dấu vết và bút toán điều chỉnh theo chính sách |
| Khôi phục dữ liệu cũ | Mất giao dịch đã xác nhận hoặc phát lại tác vụ | Mục tiêu độ bền, recovery và đối soát tương thích |

Các kịch bản phải được liên kết tới tài sản và chức năng cụ thể. Câu “dùng transaction để an toàn” chưa xác định được rủi ro nào đã được xử lý và rủi ro nào còn tồn tại.

## 5. Ràng buộc nội dung được cho phép với nội dung thực hiện

### 5.1. Máy chủ tạo nội dung chuẩn

Không dùng trực tiếp tổng tiền, phí hoặc trạng thái do client tính để ra quyết định cuối. Client có thể gửi đề nghị, còn máy chủ phải xác minh hoặc tính lại từ nguồn có thẩm quyền.

Một snapshot giao dịch có thể gồm:

```json
{
  "transaction_id": "txn-8042",
  "tenant_id": "tenant-07",
  "source_account_id": "account-18",
  "destination_account_id": "account-62",
  "amount_minor": "10000",
  "fee_minor": "100",
  "total_debit_minor": "10100",
  "currency": "VND",
  "revision": 4,
  "pricing_policy_version": "fee-policy-12",
  "confirmation_expires_at": "2026-11-27T08:20:00Z"
}
```

Các số được biểu diễn bằng chuỗi trong ví dụ để minh họa khả năng tránh mất chính xác qua các lớp trao đổi. Nếu chọn cách này, hệ thống vẫn phải parse theo quy tắc chặt, giới hạn độ dài, miền giá trị và biểu diễn chuẩn. Không phải cứ dùng chuỗi là số liệu đã an toàn.

### 5.2. Xác nhận phải gắn với giao dịch cụ thể

Xác thực lại người dùng hoặc nhập một mã xác nhận chung không tự chứng minh họ đã cho phép đúng số tiền và đúng người nhận.

Nếu nghiệp vụ yêu cầu xác nhận giao dịch, cần ràng buộc nó với ít nhất chủ thể, tenant, định danh giao dịch, revision và các thuộc tính có ý nghĩa như nguồn, đích, số tiền, đồng tiền và phí.

Trong ví dụ, snapshot được phép xác nhận trong tối đa 5 phút. Đổi người nhận, số tiền hoặc phí làm mất hiệu lực xác nhận cũ, dù thời hạn chưa hết.

Nếu dùng chữ ký hoặc digest, phải xác định biểu diễn chuẩn và cơ chế kiểm chứng phù hợp. Không tin một giá trị hash do client cung cấp là bằng chứng nội dung được phép; máy chủ cần quản lý dữ kiện và ràng buộc của chính mình.

### 5.3. Quyền vẫn phải hợp lệ tại điểm quyết định

Snapshot đã xác nhận không cấp quyền vượt chính sách hiện hành. Nếu tài khoản bị khóa hoặc quyền sử dụng đã bị thu hồi, phải xử lý theo quy tắc hiệu lực được đặc tả.

Yêu cầu cần nêu điểm quyết định, độ mới của dữ liệu quyền và hành vi với lệnh đang chạy. Nếu cần ngăn mọi commit sau thời điểm thu hồi, thiết kế phải bảo vệ điều kiện đó, thay vì chỉ kiểm tra ở đầu request.

## 6. Đặc tả số liệu và phép tính

### 6.1. Miền giá trị và đơn vị

Đối với số tiền hoặc đại lượng cần độ chính xác cao, phải quy định:

- Đơn vị lưu và trao đổi.
- Số chữ số phần thập phân cho từng loại đại lượng hoặc đồng tiền.
- Miền giá trị nhỏ nhất/lớn nhất.
- Quy tắc làm tròn và thời điểm áp dụng.
- Cách xử lý tràn số và chuyển kiểu.
- Số âm, số không hoặc giá trị vượt hạn mức có được phép không.

Không giả định mọi đồng tiền đều có hai chữ số thập phân. Không cộng trực tiếp các số thuộc các đồng tiền khác nhau để kiểm tra cân bằng nếu chưa có mô hình chuyển đổi và hạch toán tương ứng.

### 6.2. Tránh sai lệch qua các lớp

Một giá trị hợp lệ ở DB có thể bị mất chính xác khi đi qua JSON, trình duyệt, hàng đợi hoặc một thư viện số khác. Cần kiểm tra toàn bộ chuỗi biểu diễn, không chỉ kiểu cột.

Khi tính phí hoặc chiết khấu, phải nêu số liệu nguồn và quy tắc làm tròn. Ví dụ, làm tròn từng dòng rồi cộng có thể khác cộng trước rồi làm tròn. Chọn cách nào là quyết định nghiệp vụ cần được đặc tả và kiểm thử.

### 6.3. Không có giá trị mặc định nguy hiểm

Khi thiếu phí, đồng tiền hoặc thông tin nhận diện tài khoản, không tự gán một mặc định làm thay đổi ý nghĩa giao dịch mà client không biết.

Tương tự, lỗi parse không được biến thành số không; tràn số không được tạo giá trị âm hoặc nhỏ hơn để vượt kiểm tra hạn mức.

## 7. Tính nguyên tử trong ranh giới dữ liệu

### 7.1. Chọn đúng tập thay đổi cần cùng commit

Trong ví dụ chuyển nội bộ, một đơn vị commit có thể gồm:

- Định danh và kết quả giao dịch.
- Ghi nợ tài khoản nguồn.
- Ghi có tài khoản nhận và tài khoản phí.
- Các bút toán tương ứng.
- Cập nhật phần hạn mức hoặc reservation liên quan.
- Bằng chứng hoặc ý định audit bền vững theo chính sách.
- Bản ghi outbox nếu các hệ thống khác cần nhận sự kiện.

Nếu một thay đổi bắt buộc thất bại, không để các thay đổi còn lại thành kết quả được chấp nhận.

### 7.2. Luồng xử lý khái niệm

```text
begin transaction trong kho có thẩm quyền

    ràng buộc định danh lệnh và kiểm tra kết quả lặp
    lấy dữ kiện quyền, snapshot và tài khoản theo cơ chế nhất quán
    kiểm tra revision, xác nhận, tenant và trạng thái tài khoản
    kiểm tra/giữ nguồn tiền cùng hạn mức theo bảo đảm cạnh tranh

    tạo giao dịch nghiệp vụ
    ghi nợ, ghi có và các bút toán
    kiểm tra các bất biến bắt buộc
    ghi kết quả lệnh cùng ý định sự kiện/audit cần thiết

commit

chỉ trả SUCCESS khi điều kiện độ bền theo hợp đồng đã đạt
```

Đây là mô hình trách nhiệm, không phải mã cho một hệ quản trị cụ thể. Thứ tự khóa và kỹ thuật thực hiện phải phù hợp với kho dữ liệu, mức cô lập và bất biến.

### 7.3. Transaction DB không tự sửa thiết kế sai

Một transaction có thể commit cả ba số sai nếu ứng dụng không kiểm tra chúng. Một constraint duy nhất trên ID không ngăn người nhận bị thay đổi sau xác nhận.

Ràng buộc DB như khóa duy nhất, khóa ngoại, miền giá trị và điều kiện cập nhật là các lớp thực thi hữu ích, nhưng cần ánh xạ rõ tới bất biến nghiệp vụ.

Những điều kiện không thể biểu diễn bằng một constraint đơn phải được bảo vệ bằng thiết kế transaction, quyền ghi, quy trình và kiểm thử tương ứng.

## 8. Cạnh tranh, số dư và hạn mức

### 8.1. Kiểm tra rồi ghi là chưa đủ

```text
Số dư khả dụng ban đầu: 100

Lệnh A đọc 100, muốn ghi nợ 80 → kiểm tra đạt
Lệnh B đọc 100, muốn ghi nợ 80 → kiểm tra đạt

Nếu không có bảo vệ cạnh tranh:
    cả hai có thể cùng thực hiện và vi phạm chính sách
```

Cần cơ chế làm cho điều kiện số dư và thay đổi tương ứng cùng có hiệu lực an toàn. Các lựa chọn có thể gồm khóa phù hợp, cập nhật có điều kiện hoặc tuần tự hóa theo tài khoản.

### 8.2. Ví dụ cập nhật có điều kiện

```sql
UPDATE account_balances
SET available_minor = available_minor - :server_total_debit,
    version = version + 1
WHERE account_id = :verified_source_account
  AND tenant_id = :verified_tenant
  AND currency = :verified_currency
  AND status = 'ACTIVE'
  AND available_minor >= :server_total_debit
  AND version = :expected_version;
```

Ứng dụng phải kiểm tra số hàng được cập nhật và xử lý xung đột. Ví dụ này chỉ minh họa bảo vệ nguồn tiền trên một bản ghi, chưa phải toàn bộ giao dịch chuyển.

Ghi có, phí, bút toán, kết quả lệnh và các ràng buộc khác vẫn cần ở cùng đơn vị commit khi yêu cầu tính nguyên tử.

### 8.3. Bất biến tổng không nằm trong một bản ghi

Hạn mức theo ngày có thể trải qua nhiều giao dịch hoặc nhiều tài khoản. Version trên một tài khoản không tự ngăn tổng toàn tenant vượt giới hạn.

Nếu quyết định dựa trên tổng của một tập bản ghi, cần cơ chế bảo vệ chính tổng hoặc phần ngân sách được giữ. Có thể dùng một bản ghi hạn mức có cập nhật nguyên tử, khóa thích hợp hoặc cơ chế tuần tự hóa khác đã được kiểm chứng.

Một truy vấn SUM rồi ghi giao dịch mới ở bước khác có thể bị tranh chấp. Không suy ra mức cô lập đủ mạnh chỉ từ việc “đã dùng transaction”.

### 8.4. Retry sau xung đột

Khi deadlock, xung đột phiên bản hoặc lỗi giao dịch có thể thử lại, phải đánh giá lại dữ kiện cần thiết. Không chạy lại phần ghi bằng snapshot quyền hoặc số dư đã lỗi thời.

Retry phải hữu hạn và có chính sách giảm tải. Mọi lần thử cùng một lệnh phải liên kết được để không tạo thêm định danh nghiệp vụ ngoài ý muốn.

## 9. Chống lặp và hợp đồng kết quả

### 9.1. Idempotency ở cấp tiếp nhận lệnh

Trong ví dụ, API giữ kết quả idempotency ít nhất 24 giờ cho phạm vi đã định nghĩa. Khóa được ràng buộc với tenant, chủ thể hoặc phạm vi danh tính được duyệt, loại thao tác và nội dung lệnh chuẩn.

Các trường hợp cần đặc tả:

| Trường hợp | Kết quả cần có |
| --- | --- |
| Cùng khóa, cùng nội dung, kết quả đã commit | Trả lại kết quả theo hợp đồng, không hạch toán lại |
| Cùng khóa, nội dung khác | Từ chối xung đột, không đổi ý nghĩa lệnh cũ |
| Cùng khóa đang xử lý | Phản hồi đang xử lý hoặc chờ có giới hạn theo hợp đồng |
| Khóa khác nhưng cùng định danh giao dịch nghiệp vụ | Vẫn áp dụng quy tắc chống lặp của giao dịch |
| Người khác dùng khóa đoán được | Không được đọc kết quả ngoài quyền |
| Khóa đã hết thời gian lưu | Không được phá bất biến chống lặp ở cấp nghiệp vụ |

Thời hạn 24 giờ chỉ là ví dụ chính sách tiếp nhận. Định danh giao dịch và ràng buộc không hạch toán lặp không được tự mất hiệu lực sau 24 giờ nếu nghiệp vụ vẫn cấm thực hiện lại.

### 9.2. Phản hồi phải đúng mức hoàn tất

Cần phân biệt ít nhất:

- Đã tiếp nhận lệnh.
- Đang chờ xử lý hoặc chờ kết quả bên ngoài.
- Đã commit kết quả nội bộ theo hợp đồng.
- Đã hoàn tất nghiệp vụ đầu cuối.
- Bị từ chối.
- Chưa xác định được kết quả, cần đối soát.

Một API bất đồng bộ không được trả nội dung khiến client hiểu “đã chuyển xong” chỉ vì lệnh đã vào queue. Mã HTTP cũng cần đi cùng schema và mô tả trạng thái rõ ràng.

### 9.3. Mất phản hồi sau commit

Nếu commit thành công nhưng kết nối bị đứt trước khi client nhận được, client có thể thấy lỗi dù thay đổi đã xảy ra. Hệ thống cần cho truy vấn bằng định danh lệnh hoặc retry theo cùng khóa.

Không hoàn tác hoặc tạo lệnh mới chỉ vì không gửi được response. Đó là sự cố truyền kết quả, chưa phải bằng chứng transaction đã thất bại.

## 10. Giao dịch nhiều hệ thống và tác dụng phụ

### 10.1. Không giả định có transaction chung

Một transaction DB cục bộ thường không bao trùm lời gọi mạng tới hệ thống thanh toán, kho hàng hoặc dịch vụ gửi tin.

Hai thứ tự đơn giản đều có khoảng trống:

```text
Ghi DB trước → tiến trình chết trước khi gọi bên ngoài.
Gọi bên ngoài trước → bên ngoài thành công nhưng ghi DB thất bại.
```

Yêu cầu phải xác định trạng thái trung gian hợp lệ, dữ liệu bền vững và cách đối soát khi chưa biết kết quả.

### 10.2. Outbox và xử lý lặp

Có thể ghi trạng thái cùng bản ghi ý định gửi sự kiện trong một transaction cục bộ. Worker gửi từ outbox, và consumer xử lý theo định danh ổn định.

Outbox không tự bảo đảm mỗi hệ thống chỉ nhìn thấy sự kiện một lần. Khi phát lại, consumer cần ghi dấu xử lý và thay đổi dữ liệu với bảo đảm nguyên tử phù hợp, hoặc cơ chế tương đương.

Chống lặp theo event ID cũng chưa đủ nếu hai event ID khác nhau mô tả cùng một giao dịch nghiệp vụ không được phép lặp. Cần ràng buộc cả ý nghĩa nghiệp vụ.

### 10.3. Timeout bên ngoài là kết quả chưa rõ

Khi bên ngoài nhận lệnh nhưng phản hồi bị mất, phải giữ liên kết với cùng định danh nghiệp vụ và tra cứu/đối soát theo khả năng giao thức.

Nếu bên ngoài hỗ trợ idempotency, việc sử dụng phải đúng phạm vi và thời hạn hỗ trợ. Nếu không có bảo đảm đó, thiết kế cần biện pháp khác hoặc ghi nhận giới hạn; không tự tuyên bố có xử lý đúng một lần đầu cuối.

Không gửi lệnh mới với định danh mới chỉ để “thử lại cho chắc”. Việc đó có thể biến sự cố mạng thành tác dụng phụ lặp.

### 10.4. Bù trừ không phải rollback tức thời

Trong một quy trình nhiều dịch vụ, có thể dùng hành động bù để xử lý một phần đã thành công. Nhưng hành động bù có thể thất bại, bị giới hạn hoặc không đảo ngược hoàn toàn hậu quả.

Hoàn tiền là một giao dịch mới cần quyền, định danh và audit; nó không xóa việc tiền đã từng được chuyển. Thu hồi thông báo cũng không làm người nhận quên nội dung đã đọc.

Vì vậy cần đặc tả điều kiện bù, người thực hiện, thời hạn, trạng thái chờ và đối soát. Không mô tả “rollback toàn hệ thống” nếu thực tế chỉ có một chuỗi hành động bù không nguyên tử.

## 11. Độ bền, audit và đối soát

### 11.1. Định nghĩa mô hình lỗi cho giao dịch đã xác nhận

Cần nêu giao dịch đã trả SUCCESS phải sống sót qua sự cố nào: tiến trình chết, một node mất, mất điện cụm lưu trữ hay mất cả vùng.

Commit thành công trên một node không tự bảo đảm không mất dữ liệu khi toàn bộ vùng bị phá hủy. Nếu nghiệp vụ yêu cầu không mất giao dịch đã xác nhận trong kịch bản đó, kiến trúc độ bền và phục hồi phải được thiết kế, cấu hình và kiểm thử tương ứng.

RPO của hệ thống backup phải tương thích với cách công bố kết quả giao dịch. Không đồng thời hứa “không mất giao dịch đã xác nhận khi mất vùng” và dựa duy nhất vào bản sao có thể chậm 15 phút, trừ khi có cơ chế khác đáp ứng phần bảo đảm còn lại.

### 11.2. Audit phản ánh kết quả bền vững

Dấu vết nên liên kết:

- Tenant, chủ thể và quyền hoặc phiên bản chính sách liên quan.
- Định danh lệnh, định danh giao dịch và revision được thực hiện.
- Nguồn, đích, số liệu và đồng tiền theo phạm vi được phép ghi.
- Kết quả từ chối, commit, chờ hoặc chưa rõ.
- Bút toán, sự kiện và tham chiếu kết quả bên ngoài.
- Mốc thời gian cùng correlation ID phục vụ truy vết.

Không ghi log thành công trước commit rồi coi đó là bằng chứng hạch toán. Nếu transaction rollback, log ứng dụng bên ngoài transaction có thể vẫn tồn tại.

Audit cũng cần bảo vệ dữ liệu nhạy cảm và quyền sửa/xóa. Không ghi credential, token xác nhận hoặc payload đầy đủ chỉ để “dễ điều tra”.

### 11.3. Đối soát phải sâu hơn kiểm tra tổng

Một quy trình đối soát cần kiểm tra:

- Mỗi giao dịch được chấp nhận có đủ bút toán và trạng thái cần thiết.
- Tổng bút toán cân bằng theo từng đồng tiền và mô hình sổ.
- Đúng tài khoản nguồn, đích, phí và revision.
- Số dư hoặc bản tổng hợp khớp nguồn có thẩm quyền tại điểm cắt nhất quán.
- Mỗi tác dụng bên ngoài có tham chiếu phù hợp và không bị ghi nhận lặp.
- Giao dịch treo hoặc chưa rõ được xử lý theo thời hạn.

Không dùng read model cập nhật trễ để kết luận có sai lệch vĩnh viễn khi chưa xét watermark hoặc độ trễ cho phép. Ngược lại, độ trễ không được trở thành lý do để bỏ qua sai lệch vô thời hạn.

### 11.4. Sửa sai có dấu vết

Nếu mô hình sổ yêu cầu giữ lịch sử, điều chỉnh được thực hiện bằng bản ghi hoặc bút toán bổ sung có liên kết và phê duyệt, thay vì âm thầm sửa số cũ.

Cần phân tách quyền thực hiện giao dịch, đối soát và điều chỉnh theo mức rủi ro. Một tài khoản có thể vừa tạo giao dịch vừa xóa bằng chứng sẽ làm yếu khả năng kiểm chứng toàn vẹn.

## 12. Bộ yêu cầu bảo mật minh họa

Các yêu cầu dưới đây áp dụng cho ví dụ chuyển nội bộ và phần tích hợp được xác định. Khi chuyển thành đặc tả dự án, phải gắn với danh mục tài khoản, nguồn quyền, kho dữ liệu và mô hình lỗi thực tế.

| ID | Yêu cầu có thể kiểm chứng | Chủ sở hữu | Bằng chứng đạt |
| --- | --- | --- | --- |
| TIN-01 | Máy chủ phải xác định hoặc xác minh nguồn, đích, số tiền, đồng tiền, phí và quyền theo nguồn có thẩm quyền; không tin tổng do client tự tính. | Ứng dụng/bảo mật | Sửa từng trường đầu vào không làm phát sinh giao dịch khác nội dung được phép. |
| TIN-02 | Xác nhận phải gắn với snapshot và revision; trong ví dụ hết hiệu lực sau 5 phút hoặc ngay khi nội dung ràng buộc thay đổi. | Nghiệp vụ/ứng dụng | Xác nhận cũ, hết hạn hoặc đổi người nhận không được dùng để thực hiện. |
| TIN-03 | Kiểu số, đơn vị, miền giá trị, làm tròn và tràn số phải được định nghĩa thống nhất qua API, DB và sự kiện. | Ứng dụng/dữ liệu | Kiểm tra ranh giới, chuyển đổi và chuỗi serialize/parse không làm đổi ý nghĩa. |
| TIN-04 | Ghi nợ, ghi có, phí, bút toán, kết quả lệnh và dữ kiện bắt buộc phải cùng commit trong phạm vi chuyển nội bộ. | Dữ liệu/ứng dụng | Tiêm lỗi tại từng điểm ghi; không có trạng thái nghiệp vụ một phần được chấp nhận. |
| TIN-05 | Sau mỗi giao dịch commit, bút toán phải cân bằng theo đồng tiền, đúng nội dung được phép và không gây số dư khả dụng âm trong chính sách ví dụ. | Nghiệp vụ/dữ liệu | Đối chiếu bản ghi và số dư, gồm tải cạnh tranh và trường hợp bị từ chối. |
| TIN-06 | Số dư, reservation và hạn mức tổng phải được bảo vệ trước các lệnh đồng thời; retry sau xung đột phải đánh giá lại guard. | Dữ liệu | Hai lệnh cạnh tranh phần nguồn không đủ không thể cùng vi phạm bất biến. |
| TIN-07 | API giữ kết quả idempotency ít nhất 24 giờ trong ví dụ; khóa ràng buộc phạm vi và nội dung, cùng khóa khác nội dung không được thực hiện mới. | Ứng dụng | Test retry, mất phản hồi, khóa trùng và quyền đọc kết quả. |
| TIN-08 | Chống lặp theo định danh giao dịch nghiệp vụ phải tiếp tục có hiệu lực theo vòng đời nghiệp vụ, kể cả khi đổi hoặc hết hạn khóa API. | Ứng dụng/dữ liệu | Khóa khác hoặc event khác không tạo thêm hạch toán bị cấm cho cùng giao dịch. |
| TIN-09 | Phản hồi phải phân biệt tiếp nhận, commit nội bộ, hoàn tất, từ chối và chưa rõ; không trả hoàn tất khi mới đưa vào queue. | Chủ API | Contract test và kiểm tra dữ kiện thực tế tại từng phản hồi. |
| TIN-10 | Giao dịch đã xác nhận phải có độ bền theo mô hình lỗi được duyệt; phục hồi phải kiểm chứng được các giao dịch đã trả SUCCESS trong phạm vi đó. | Nền tảng/dữ liệu | Thử crash và phục hồi bằng danh sách marker đã được client xác nhận. |
| TIN-11 | Với hệ thống ngoài, ý định, lần thử và kết quả phải truy vết được; timeout không được tự dẫn đến lệnh mới có thể gây tác dụng phụ lặp. | Tích hợp | Mất phản hồi, khởi động lại worker và đối soát vẫn khớp một giao dịch logic theo chính sách. |
| TIN-12 | Audit và đối soát phải xác minh số liệu lẫn nguồn/đích/revision; điều chỉnh không được che mất lịch sử theo mô hình sổ đã chọn. | Vận hành/bảo mật | Đếm và đối chiếu đầy đủ; thay người nhận hoặc sửa lịch sử bị phát hiện/ngăn chặn theo thiết kế. |
| TIN-13 | Bất biến và giao dịch chưa rõ phải có lịch kiểm tra, thời hạn cảnh báo và chủ xử lý; thiếu dữ liệu đối soát không được báo là đã đạt. | Vận hành | Tiêm sai lệch hoặc dừng luồng đối soát; quan sát trạng thái và thông báo đúng hạn. |
| TIN-14 | Mọi đường ghi, gồm API, worker, nhập dữ liệu và công cụ quản trị, phải tuân thủ các bất biến tương đương; thay đổi kiến trúc phải cập nhật test. | Chủ dịch vụ | Kiểm kê đường ghi và bằng chứng cho từng đường, không chỉ endpoint chính. |

Đối với TIN-13, một cấu hình minh họa là kiểm tra bất biến nội bộ mỗi 60 giây và phát cảnh báo trong 120 giây từ lúc sai lệch có thể quan sát ổn định trong bài thử. Hệ thống đối soát bên ngoài cần thời hạn riêng theo độ trễ và điểm cắt dữ liệu, không áp cùng ngưỡng một cách máy móc.

Nếu thiếu luồng dữ liệu hoặc không có điểm cắt đủ tin cậy, trạng thái phải là chưa xác định hoặc mất khả năng đối soát. Không loại trường hợp đó khỏi báo cáo để giữ tỷ lệ đạt.

### Mẫu đặc tả chi tiết

```text
ID: TIN-04
Mục tiêu: không có chuyển nội bộ được ghi nhận một phần
Rủi ro: R-TX-02 — ghi nợ thành công nhưng ghi có hoặc kết quả lệnh thất bại
Phạm vi: chuyển cùng tenant, cùng đồng tiền, trong kho được chỉ định
Tập thay đổi bắt buộc:
  - Giao dịch và kết quả lệnh
  - Ghi nợ, ghi có, phí và bút toán
  - Reservation/hạn mức liên quan
  - Ý định sự kiện và bằng chứng bền vững theo chính sách
Điều kiện:
  - Tất cả cùng commit, hoặc không có kết quả một phần được chấp nhận
  - Chỉ trả SUCCESS khi đã đạt hợp đồng commit và độ bền
Ngoài phạm vi:
  - Không mặc định transaction cục bộ bao phủ dịch vụ ngoài
Chủ sở hữu: đội dữ liệu, phối hợp đội ứng dụng
Kiểm thử: T-TIN-03, T-TIN-04, T-TIN-08
Bằng chứng: failpoint, trạng thái DB, bút toán, audit và phản hồi
```

## 13. Ma trận kiểm thử nghiệm thu

Thử trong môi trường kiểm soát với dữ liệu giả và hệ thống ngoài giả lập hoặc sandbox. Test cạnh tranh cần điểm đồng bộ hoặc lịch thực thi có thể quan sát; gửi nhiều request ngẫu nhiên mà chưa gặp lỗi không phải bằng chứng guard đúng.

| Test ID | Điều kiện thử | Kết quả mong đợi | Truy vết |
| --- | --- | --- | --- |
| T-TIN-01 | Đổi số tiền, phí, đồng tiền, nguồn hoặc đích sau khi tạo snapshot/xác nhận. | Không thực hiện nội dung mới bằng xác nhận cũ; quyền và tenant được giữ đúng. | TIN-01, 02 |
| T-TIN-02 | Giá trị âm, không, vượt biên, nhiều chữ số, biểu diễn không chuẩn và ranh giới làm tròn. | Xử lý đúng miền giá trị; không tràn số hoặc mất chính xác qua các lớp. | TIN-03 |
| T-TIN-03 | Tiêm lỗi lần lượt sau ghi nợ, ghi có, phí, bút toán và trước commit. | Không còn tổ hợp commit một phần; kết quả bị từ chối/rollback không gây hạch toán ngoài ý muốn. | TIN-04, 05 |
| T-TIN-04 | Hai lệnh cùng đọc nguồn/hạn mức chỉ đủ một lệnh; thêm trường hợp nhiều tài khoản dùng chung quota. | Bất biến tổng được giữ; retry đánh giá lại dữ kiện; không số dư âm ngoài chính sách. | TIN-05, 06 |
| T-TIN-05 | Cùng khóa cùng payload, cùng khóa khác payload, khóa khác cùng giao dịch và khóa đã hết hạn. | Đúng hợp đồng idempotency; không hạch toán lặp hoặc lộ kết quả ngoài quyền. | TIN-07, 08 |
| T-TIN-06 | Commit thành công rồi làm mất response; client truy vấn hoặc retry. | Truy xuất được kết quả cũ, không tạo giao dịch mới do mất phản hồi. | TIN-07, 09 |
| T-TIN-07 | Bên ngoài nhận lệnh nhưng phản hồi mất; worker restart và nhận event lặp. | Theo dõi trạng thái chưa rõ, dùng định danh ổn định và đối soát; không tự nhân tác dụng phụ. | TIN-08, 11 |
| T-TIN-08 | Crash tại các điểm trước/sau commit theo mô hình lỗi được duyệt; phục hồi rồi đối chiếu marker. | Giao dịch đã xác nhận được giữ đúng cam kết; không có thành công giả hoặc trạng thái nửa vời. | TIN-04, 10 |
| T-TIN-09 | Gửi sự kiện sai nguồn, sai giao dịch, sai dữ kiện hoặc đến sai thứ tự. | Không ghi nhận sai kết quả; sự kiện cần đối soát được giữ dấu vết và không làm lùi trạng thái trái phép. | TIN-11, 12 |
| T-TIN-10 | Tạo sai lệch có kiểm soát trong dữ liệu thử: tổng cân bằng nhưng sai người nhận; thiếu một bút toán; projection cập nhật trễ. | Đối soát phân biệt lỗi ngữ nghĩa với độ trễ và phát hiện cả trường hợp tổng vẫn bằng không. | TIN-05, 12, 13 |
| T-TIN-11 | Thử điều chỉnh lịch sử bằng vai trò không được phép, rồi bằng quy trình điều chỉnh hợp lệ. | Ngăn sửa trái quyền; giữ liên kết điều chỉnh và bằng chứng theo chính sách. | TIN-12 |
| T-TIN-12 | Dừng luồng đối soát hoặc mất dữ liệu tham chiếu; chạy giao dịch qua batch/worker/công cụ quản trị. | Báo mất khả năng kiểm chứng đúng hạn; các đường ghi vẫn giữ bất biến. | TIN-13, 14 |

Nghiệm thu phải đối chiếu phản hồi, dữ liệu đã commit, bút toán, số dư và tác dụng bên ngoài. Một response lỗi không chứng minh giao dịch chưa có hiệu lực; một response thành công cũng không đủ chứng minh toàn vẹn.

Báo cáo cần ghi phiên bản ứng dụng, schema, chính sách, cấu hình độ bền, lịch thực thi, marker, kết quả và giới hạn của mô hình lỗi. Những điều chưa kiểm chứng không được tính là đạt theo suy đoán.

## 14. Truy vết yêu cầu trong vòng đời phát triển

Chuỗi truy vết tối thiểu:

```text
Mục tiêu bảo mật và ý nghĩa giao dịch
    → Kịch bản sửa nội dung, cạnh tranh, lặp hoặc mất kết quả
    → Bất biến và mô hình lỗi
    → Yêu cầu TIN-xx
    → Thiết kế dữ liệu, quyền, transaction và giao thức tích hợp
    → Test T-TIN-xx
    → Audit, đối soát và quy trình sửa sai
```

| Mục tiêu | Rủi ro | Yêu cầu | Thiết kế/kiểm chứng |
| --- | --- | --- | --- |
| Thực hiện đúng nội dung được cho phép | Sửa người nhận hoặc số tiền sau xác nhận | TIN-01, 02 | Snapshot và revision; T-TIN-01 |
| Không có hạch toán thiếu/thừa | Ghi một phần hoặc tranh số dư | TIN-04, 05, 06 | Đơn vị commit và guard cạnh tranh; T-TIN-03, 04 |
| Không tạo tác dụng lặp | Retry và timeout | TIN-07, 08, 11 | Định danh nghiệp vụ, idempotency, đối soát; T-TIN-05, 06, 07 |
| Không mất giao dịch đã xác nhận ngoài cam kết | Crash hoặc phục hồi không đủ độ bền | TIN-10 | Mô hình lỗi và marker client; T-TIN-08 |
| Phát hiện và sửa sai có dấu vết | Sai người nhận nhưng tổng vẫn cân bằng | TIN-12, 13 | Đối soát ngữ nghĩa và điều chỉnh kiểm soát; T-TIN-10, 11 |

Khi đổi phí, cách làm tròn, nguồn quyền, mức cô lập, queue, số node hoặc nhà cung cấp thanh toán, phải đánh giá lại các bất biến và test liên quan.

Ngoại lệ cần phạm vi, rủi ro còn lại, biện pháp bù, người phê duyệt và thời hạn. Không bỏ một đường ghi khỏi danh mục chỉ vì khó đưa vào transaction hiện tại.

## 15. Những lỗi đặc tả thường gặp

| Cách viết hoặc suy luận | Vấn đề | Cách cải thiện |
| --- | --- | --- |
| “Có ACID nên giao dịch đúng.” | Kho dữ liệu không tự biết nghiệp vụ hoặc quyền | Định nghĩa bất biến và nội dung được phép trước |
| “TLS ngăn sửa số tiền.” | Client có thể chủ động gửi số tiền sai | Tính/xác minh từ nguồn có thẩm quyền |
| “Tổng bằng không nghĩa là hợp lệ.” | Có thể ghi đúng tổng nhưng sai tài khoản | Đối chiếu cả nguồn, đích, phí và revision |
| “OTP xác nhận mọi thao tác trong phiên.” | Không ràng buộc một nội dung giao dịch cụ thể | Gắn xác nhận với snapshot, chủ thể và thời hạn |
| “Timeout thì thực hiện lại bằng ID mới.” | Lệnh cũ có thể đã thành công | Tra cứu/đối soát theo cùng định danh |
| “Có idempotency key nên không thể lặp.” | Khóa khác hoặc hết hạn vẫn có thể trùng nghiệp vụ | Chống lặp ở cấp giao dịch logic |
| “Outbox cho exactly once đầu cuối.” | Giao nhận và tác dụng ngoài có thể lặp | Consumer idempotent, định danh ổn định và đối soát |
| “Gọi API ngoài trong transaction là nguyên tử.” | Rollback DB không hoàn tác bên ngoài | Mô hình trạng thái trung gian và tác dụng phụ riêng |
| “Bù trừ giống rollback.” | Bù trừ có thể thất bại hoặc không đảo hết hậu quả | Quy trình bù có quyền, trạng thái, thời hạn và audit |
| “Backup mỗi ngày là đủ cho SUCCESS.” | Có thể mất giao dịch đã xác nhận ngoài mức công bố | Liên kết độ bền, mô hình lỗi và recovery |

## 16. Bài tập áp dụng

Một nền tảng bán hàng cho phép tạo đơn, áp khuyến mãi, giữ tồn kho và thanh toán qua bên ngoài. Client gửi tổng tiền; worker retry khi timeout. Một số đơn bị ghi nhận thanh toán hai lần, trong khi một số khác đã thu tiền nhưng không có sự kiện hoàn tất.

Hãy thực hiện:

1. Xác định nội dung giao dịch do máy chủ quyết định và nội dung cần người dùng xác nhận.
2. Viết năm bất biến, gồm tổng tiền, hạn mức khuyến mãi, tồn kho và thanh toán không lặp.
3. Chỉ ra tập thay đổi có thể cùng commit và các tác dụng ngoài ranh giới transaction.
4. Thiết kế định danh lệnh, định danh nghiệp vụ, idempotency và trạng thái chưa rõ.
5. Viết sáu yêu cầu có ID, phạm vi, điều kiện đạt, chủ sở hữu và bằng chứng.
6. Thiết kế test cho sửa tổng tiền, chiếm lượt khuyến mãi đồng thời, lỗi trước/sau commit và mất phản hồi của bên thanh toán.
7. Đề xuất đối soát phát hiện đơn đúng tổng nhưng sai người nhận, đơn đã thu tiền nhưng thiếu sự kiện và tác dụng lặp.
8. Nêu cam kết độ bền cho giao dịch đã trả thành công trong mô hình lỗi được chọn.

Đáp án tốt cần giải thích vì sao các bất biến vẫn đúng khi có cạnh tranh và lỗi, thay vì chỉ liệt kê công nghệ như DB, queue hoặc cache.

## 17. Checklist chấp nhận yêu cầu

- Ý nghĩa giao dịch, chủ thể, nguồn và đích đã được xác định rõ chưa?
- Số tiền, phí, đơn vị và quy tắc làm tròn có nguồn có thẩm quyền không?
- Xác nhận có gắn với đúng nội dung và revision không?
- Quyền và trạng thái có còn hợp lệ tại điểm quyết định không?
- Tập thay đổi phải cùng commit đã đầy đủ chưa?
- Số dư và hạn mức tổng có được bảo vệ trước cạnh tranh không?
- Retry có kiểm tra lại guard và giữ cùng ý nghĩa giao dịch không?
- Idempotency API và chống lặp nghiệp vụ có được đặc tả riêng không?
- Phản hồi có phân biệt tiếp nhận, commit, hoàn tất và chưa rõ không?
- Tác dụng ngoài có định danh ổn định và đường đối soát không?
- Độ bền của SUCCESS có tương thích với mô hình lỗi và recovery không?
- Audit và đối soát có phát hiện sai ngữ nghĩa, không chỉ sai tổng không?
- Điều chỉnh có quyền, liên kết và dấu vết thay vì che lịch sử không?
- Test có kiểm tra dữ liệu và tác dụng thực tế trên mọi đường ghi không?

Tính toàn vẹn giao dịch được bảo đảm bằng việc ràng buộc quyết định được phép với thay đổi thực tế, giữ các bất biến qua cạnh tranh và lỗi, đồng thời cung cấp bằng chứng đủ để phát hiện và xử lý mọi kết quả chưa khớp.
