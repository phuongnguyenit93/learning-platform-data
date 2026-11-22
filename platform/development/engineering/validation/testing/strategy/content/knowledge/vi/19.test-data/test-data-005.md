# Cô lập dữ liệu giữa ca, nhóm thực thi và môi trường

Dữ liệu kiểm thử thường được dùng lại bởi nhiều test case, nhiều worker chạy song song và nhiều môi trường. Nếu một lần chạy thay đổi dữ liệu mà lần chạy khác đang đọc, kết quả có thể phụ thuộc vào thứ tự thực thi, thời điểm hoặc trạng thái còn sót lại. Test có thể pass khi chạy riêng nhưng fail khi chạy cả suite; lỗi có thể xuất hiện ở staging nhưng không tái hiện được ở local; hoặc một test vô tình xóa dữ liệu mà nhóm khác đang cần.

Cô lập dữ liệu kiểm thử là cách tổ chức dữ liệu, tài nguyên và trạng thái sao cho mỗi ca kiểm thử, nhóm thực thi hoặc môi trường chỉ tác động đến phần dữ liệu thuộc phạm vi của mình. Cô lập tốt giúp kết quả ổn định, hỗ trợ chạy song song, giảm rò rỉ dữ liệu giữa môi trường và làm cho lỗi có thể tái hiện. Cô lập không nhất thiết đòi hỏi một database riêng cho mọi test; cần chọn ranh giới phù hợp với mức độ chia sẻ, chi phí và rủi ro.

## 1. Hiểu các cấp độ cô lập dữ liệu

Dữ liệu có thể cần được cô lập ở nhiều cấp. Một test case có thể tạo bản ghi riêng trong một database dùng chung; một nhóm test có thể dùng schema riêng; một worker có thể có namespace riêng; còn mỗi môi trường có thể dùng một cụm dữ liệu và thông tin xác thực tách biệt.

| Cấp độ | Phạm vi cần cô lập | Ví dụ |
|---|---|---|
| Test case | Dữ liệu được tạo hoặc thay đổi bởi một ca kiểm thử | Một đơn hàng có mã duy nhất cho test tạo đơn |
| Test suite / nhóm thực thi | Các test chạy cùng nhau hoặc theo một chức năng | Bộ kiểm thử thanh toán dùng một namespace riêng |
| Worker / tiến trình | Các test chạy song song trên nhiều worker | Mỗi worker có schema hoặc tenant riêng |
| Test run / pipeline | Một lần chạy CI hoặc một lần xác minh release | Dữ liệu gắn với mã run và được dọn sau khi hoàn tất |
| Môi trường | Dữ liệu và cấu hình của local, integration, staging hoặc production | Database staging tách khỏi database production |
| Tổ chức / tenant | Dữ liệu giữa khách hàng hoặc đơn vị sử dụng | Tenant A không đọc hoặc sửa dữ liệu tenant B |

Các cấp độ này có thể kết hợp. Ví dụ, mỗi pipeline có một database tạm thời; trong database đó, mỗi worker có schema riêng; mỗi test case tạo các bản ghi mang mã định danh riêng. Việc lựa chọn phụ thuộc vào khả năng của hệ thống, thời gian tạo tài nguyên và mức rủi ro khi dữ liệu bị chia sẻ.

Cần phân biệt cô lập dữ liệu với phân quyền dữ liệu. Cô lập trong kiểm thử nhằm tránh các hoạt động kiểm thử ảnh hưởng lẫn nhau; kiểm soát phân quyền nhằm ngăn truy cập trái phép. Một hệ thống có namespace riêng nhưng quyền truy cập không được kiểm tra vẫn có thể tồn tại lỗ hổng phân quyền.

## 2. Vì sao dữ liệu dùng chung làm kiểm thử không ổn định?

Khi test phụ thuộc vào trạng thái được tạo bởi test khác, kết quả không còn độc lập. Một số biểu hiện thường gặp:

- Test pass khi chạy riêng nhưng fail khi chạy toàn bộ suite.
- Thứ tự test làm thay đổi kết quả.
- Hai worker cùng cập nhật một bản ghi và ghi đè dữ liệu của nhau.
- Test cleanup xóa bản ghi mà test khác đang sử dụng.
- Một test giả định dữ liệu ban đầu luôn tồn tại nhưng test trước đã thay đổi hoặc xóa nó.
- Dữ liệu cũ từ lần chạy trước làm test mới có kết quả sai.
- Một môi trường dùng chung bị nhóm khác thay đổi cấu hình hoặc dữ liệu trong khi test đang chạy.
- Sự kiện, queue hoặc file còn sót lại khiến lần chạy tiếp theo xử lý nhầm dữ liệu cũ.

Ví dụ, hai test cùng dùng email buyer@example.test để tạo tài khoản. Test thứ nhất đăng ký thành công; test thứ hai thất bại vì email đã tồn tại. Nếu test thứ nhất xóa tài khoản ngay khi hoàn tất, test thứ hai có thể thành công hoặc thất bại tùy thời điểm. Kết quả phụ thuộc lịch thực thi thay vì hành vi sản phẩm.

Một nguyên tắc hữu ích là mỗi test phải tự chuẩn bị dữ liệu mà nó cần, chỉ thay đổi dữ liệu thuộc quyền sở hữu của nó và có cách dọn hoặc hết hạn trạng thái sau khi chạy. Test không nên dựa vào việc một test khác đã chạy trước đó để tạo dữ liệu đầu vào.

## 3. Xác định ranh giới chia sẻ trước khi chọn kỹ thuật

Trước khi thiết kế cô lập, lập danh sách các tài nguyên có trạng thái mà test có thể đọc hoặc thay đổi:

- Bản ghi trong database và quan hệ giữa chúng.
- Schema, bảng tạm, sequence và transaction.
- File, object storage và thư mục dùng chung.
- Queue, topic, subscription và consumer group.
- Cache, key-value store và session.
- Tài khoản, token, quyền và cấu hình.
- Dữ liệu do dịch vụ bên ngoài tạo ra.
- Đồng hồ, lịch, khóa phân tán và tài nguyên có giới hạn.
- Feature flag, biến môi trường và cấu hình runtime.

Với mỗi tài nguyên, xác định ai sở hữu, ai được đọc, ai được ghi, thời gian tồn tại và cách khôi phục. Nếu hai nhóm cùng cần đọc fixture chuẩn nhưng không được sửa nó, có thể chia sẻ dữ liệu bất biến. Nếu cả hai cần thay đổi cùng một đối tượng, nên tạo bản sao hoặc namespace riêng.

Cần xác định cả các phụ thuộc gián tiếp. Một test tạo đơn hàng có thể ghi database, phát event, tạo file hóa đơn, cập nhật cache và gọi sandbox thanh toán. Chỉ cô lập bảng đơn hàng là chưa đủ nếu event hoặc file vẫn dùng chung tên và bị ghi đè.

## 4. Các chiến lược cô lập phổ biến

Không có một kỹ thuật duy nhất phù hợp với mọi hệ thống. Có thể kết hợp các cách sau.

| Chiến lược | Cách hoạt động | Phù hợp khi | Giới hạn |
|---|---|---|---|
| Dữ liệu riêng theo test | Mỗi test tạo bản ghi có ID hoặc khóa duy nhất | Test dùng database chung và cần ít tài nguyên | Cần quản lý quan hệ và cleanup |
| Transaction rollback | Mỗi test chạy trong transaction rồi rollback | Các thao tác nằm trong cùng database và không thoát transaction | Không bao phủ side effect bên ngoài hoặc tác vụ ở connection khác |
| Schema/database riêng | Mỗi worker hoặc test run dùng schema/database độc lập | Cần ranh giới mạnh và có thể tạo tài nguyên nhanh | Tốn tài nguyên, cần migration và quản lý vòng đời |
| Tenant/namespace riêng | Mỗi nhóm chạy dùng tenant hoặc namespace riêng | Ứng dụng hỗ trợ đa tenant hoặc tài nguyên có namespace | Phải xác minh mọi truy vấn đều giới hạn đúng phạm vi |
| Fixture bất biến | Dùng dữ liệu chuẩn chỉ đọc, không sửa trực tiếp | Dữ liệu tham chiếu hoặc kịch bản nền ổn định | Cần bản sao khi test phải thay đổi dữ liệu |
| Môi trường tạm thời | Tạo stack hoặc database riêng cho một pipeline | Kiểm thử tích hợp có nhiều phụ thuộc | Thời gian tạo và chi phí hạ tầng cao hơn |
| Khóa tài nguyên | Chỉ một test hoặc nhóm được dùng tài nguyên tại một thời điểm | Tài nguyên không hỗ trợ bản sao hoặc namespace | Giảm khả năng chạy song song và cần timeout khóa |

Lựa chọn nên dựa trên ranh giới tác động. Với một unit test tính toán thuần, không cần tạo database riêng. Với kiểm thử migration hoặc tương tác nhiều dịch vụ, một môi trường tạm thời có thể đáng giá hơn việc cố chia sẻ một staging đang được nhiều nhóm sử dụng.

## 5. Tạo dữ liệu riêng và định danh duy nhất

Một cách đơn giản để tránh xung đột là tạo dữ liệu riêng cho mỗi test hoặc test run. Mã định danh nên được tạo từ nguồn đủ duy nhất và gắn với ngữ cảnh thực thi.

Ví dụ, thay vì dùng email cố định, test có thể tạo địa chỉ dựa trên run ID và test ID:

~~~text
buyer+run-8421-test-create-order@example.test
~~~

Với tài nguyên khác, có thể dùng quy ước tương tự:

- test-8421-order-<unique-id>
- run-8421/worker-3/invoice-<unique-id>.pdf
- namespace: ci-8421-worker-3
- queue: test-8421-payment-events

Không nên chỉ dựa vào timestamp có độ phân giải thấp nếu nhiều worker có thể tạo dữ liệu cùng lúc. Có thể dùng UUID, sequence được quản lý hoặc ID do hệ thống cấp. Khi dùng ID ngẫu nhiên, lưu seed hoặc giá trị đã tạo để tái hiện lỗi.

Dữ liệu riêng cần bao gồm toàn bộ quan hệ liên quan. Một đơn hàng có thể phụ thuộc khách hàng, địa chỉ, sản phẩm, tồn kho và phương thức thanh toán. Tạo một bản ghi đơn hàng riêng nhưng dùng chung tồn kho có thể khiến test vẫn tranh chấp. Cần xác định phạm vi dữ liệu nào cần riêng và phạm vi nào có thể dùng chung ở chế độ chỉ đọc.

## 6. Dùng fixture, factory và builder có kiểm soát

Fixture là dữ liệu được chuẩn bị trước hoặc tạo theo mẫu để phục vụ kiểm thử. Factory và builder giúp tạo đối tượng với các thuộc tính cần thiết mà không phải viết lại cấu trúc dữ liệu trong từng test.

Một fixture tốt cần:

- Có mục đích và chủ sở hữu rõ ràng.
- Có thể tạo lại từ mã nguồn hoặc script có phiên bản.
- Không phụ thuộc vào trạng thái do test khác tạo.
- Có dữ liệu đủ đại diện cho trường hợp được kiểm tra.
- Có thể dùng ở chế độ chỉ đọc nếu nhiều test cần chung dữ liệu.
- Có cách tạo bản sao riêng khi test cần sửa.
- Có phiên bản hoặc định danh để biết dữ liệu nào đã được dùng.

Ví dụ pseudo-code:

~~~javascript
const customer = await customerFactory.create({
  tenantId: run.tenantId,
  status: "ACTIVE"
});

const order = await orderFactory.create({
  customerId: customer.id,
  items: [{ sku: "SKU-TEST-1", quantity: 2 }]
});
~~~

Factory nên tạo dữ liệu qua các quy tắc và ràng buộc hợp lệ của hệ thống khi mục tiêu là kiểm tra nghiệp vụ. Nếu chèn trực tiếp vào database, test có thể bỏ qua validation, event hoặc side effect mà ứng dụng bình thường phải thực hiện. Truy cập trực tiếp có thể phù hợp để chuẩn bị fixture nền hoặc kiểm tra dữ liệu, nhưng cần ghi rõ giới hạn.

Tránh một fixture khổng lồ được mọi test sửa trực tiếp. Thay vào đó, giữ dữ liệu nền bất biến và tạo bản sao hoặc đối tượng riêng cho từng ca kiểm thử.

## 7. Cô lập bằng transaction và hiểu giới hạn của rollback

Transaction rollback thường hữu ích cho kiểm thử database. Test mở transaction, thực hiện thao tác và rollback sau khi hoàn tất, nhờ đó dữ liệu không tồn tại sau lần chạy.

Ví dụ khái niệm:

~~~sql
BEGIN;

INSERT INTO test_customer (id, email)
VALUES ('customer-test-8421', 'buyer-8421@example.test');

-- Thực hiện thao tác và truy vấn xác minh trong cùng transaction.

ROLLBACK;
~~~

Cách này chỉ hoạt động khi thao tác cần kiểm tra và phần xác minh sử dụng cùng transaction hoặc cùng cơ chế quản lý transaction. Có một số giới hạn:

- Ứng dụng có thể mở connection khác nên không nhìn thấy dữ liệu chưa commit.
- Test có thể phát event, gửi email hoặc gọi dịch vụ bên ngoài; rollback database không thu hồi các tác dụng phụ đó.
- Tác vụ nền có thể chạy sau khi transaction kết thúc.
- Một số thao tác DDL hoặc sequence không rollback theo cách nhóm kỳ vọng.
- Test đồng thời có thể gặp lock hoặc isolation anomaly.
- Commit là cần thiết để kiểm tra hành vi thực tế qua nhiều service.

Vì vậy, transaction rollback phù hợp với một số kiểm thử tích hợp trong cùng database, nhưng không phải giải pháp cô lập toàn hệ thống. Với side effect, dùng fake, sandbox, outbox test hoặc cơ chế cleanup riêng.

## 8. Cô lập giữa worker và nhóm thực thi song song

Khi CI chia test cho nhiều worker, mỗi worker cần có ranh giới dữ liệu riêng hoặc cơ chế điều phối tài nguyên dùng chung.

Một cách tổ chức có thể là:

~~~text
Test run: pipeline-8421
  Worker 1: schema ci_8421_w1
  Worker 2: schema ci_8421_w2
  Worker 3: schema ci_8421_w3
  Shared: reference_catalog (read-only)
~~~

Các nguyên tắc cần áp dụng:

- Tạo namespace hoặc schema riêng trước khi worker bắt đầu.
- Truyền run ID và worker ID vào factory, log và tài nguyên.
- Không dùng ID cố định hoặc tài khoản dùng chung có thể bị sửa.
- Không để cleanup của worker này xóa tài nguyên worker khác.
- Nếu có tài nguyên không thể nhân bản, dùng khóa có thời hạn và chủ sở hữu rõ.
- Xác minh việc chạy song song không làm thay đổi kết quả so với chạy tuần tự.
- Dọn namespace theo đúng run ID khi worker kết thúc.

Nếu dùng khóa, cần có timeout, cơ chế giải phóng khi worker chết và thông tin chẩn đoán khi khóa bị giữ quá lâu. Tránh khóa toàn bộ suite nếu chỉ một tài nguyên nhỏ cần tuần tự hóa; điều đó làm giảm tốc độ mà không tăng thêm mức an toàn cần thiết.

## 9. Cô lập giữa môi trường local, CI, staging và production

Mỗi môi trường có mục đích, dữ liệu và mức quyền khác nhau. Cần ngăn việc test vô tình ghi dữ liệu vào môi trường thật hoặc dùng thông tin xác thực không đúng phạm vi.

| Môi trường | Dữ liệu nên dùng | Quyền và kiểm soát |
|---|---|---|
| Local | Dữ liệu tổng hợp nhỏ, fixture tạo nhanh | Tài khoản phát triển, phụ thuộc giả lập hoặc sandbox |
| CI / integration | Dataset có thể tạo lại, namespace theo run | Secret riêng của pipeline, quyền tối thiểu |
| Staging | Dữ liệu đại diện đã được xử lý phù hợp | Tài khoản staging, quyền giới hạn, log và cleanup |
| Pre-production | Dataset và cấu hình gần production nhưng đã kiểm soát | Quy trình phê duyệt, dữ liệu không nhạy cảm hoặc đã được bảo vệ |
| Production | Dữ liệu thật theo chính sách vận hành | Không dùng cho test phá hủy; mọi xác minh phải được phê duyệt và giới hạn |

Không dùng chung database, bucket, queue hoặc secret giữa production và môi trường thử nghiệm. Tên môi trường trong cấu hình cần rõ ràng; pipeline nên xác minh target trước khi chạy thao tác có tác động. Có thể dùng tài khoản riêng và chính sách mạng để giảm nguy cơ test kết nối nhầm.

Dữ liệu sao chép từ production cần được đánh giá về quyền riêng tư, bảo mật và tính cần thiết. Ưu tiên dữ liệu tổng hợp hoặc dữ liệu đã được xử lý phù hợp. Nếu dùng bản sao, phải kiểm soát quyền truy cập, che dữ liệu, thời hạn lưu và cách xóa.

## 10. Cô lập queue, file, cache và dịch vụ bên ngoài

Cô lập database nhưng bỏ quên tài nguyên phụ vẫn có thể gây xung đột.

### 10.1. Queue và topic

Dùng topic, queue hoặc subscription riêng theo test run nếu nền tảng hỗ trợ. Nếu phải dùng chung, gắn metadata định danh và lọc chính xác thông điệp của test. Không để consumer của test này nhận thông điệp thuộc test khác.

Khi kiểm tra retry hoặc dead-letter, xác định cách xóa hoặc lưu thông điệp sau khi chạy. Không xóa toàn bộ queue dùng chung để làm sạch một test case.

### 10.2. File và object storage

Dùng bucket hoặc prefix riêng, chẳng hạn test-runs/8421/worker-2/. Tên file phải duy nhất và cleanup chỉ được xóa đúng prefix do test sở hữu. Nếu cần kiểm tra quyền, hãy tạo tài khoản và object riêng để tránh ảnh hưởng dữ liệu khác.

### 10.3. Cache và session

Dùng key có namespace hoặc database cache riêng. Nếu test cần kiểm tra cache invalidation, phải xác định key và phạm vi xóa cụ thể. Tránh lệnh flush toàn bộ cache trên môi trường dùng chung.

### 10.4. Dịch vụ bên ngoài

Ưu tiên sandbox hoặc fake server có thể điều khiển phản hồi. Mỗi test nên dùng merchant, account hoặc resource thử nghiệm riêng nếu nhà cung cấp hỗ trợ. Ghi rõ giới hạn sandbox vì nó có thể không mô phỏng đầy đủ hành vi production.

## 11. Quản lý vòng đời dữ liệu và cleanup an toàn

Dữ liệu kiểm thử cần có vòng đời từ lúc tạo đến lúc hết hạn hoặc được xóa. Cleanup là một phần của thiết kế test, không phải việc tùy chọn thực hiện khi có thời gian.

Một vòng đời phổ biến:

1. Tạo namespace hoặc run ID.
2. Chuẩn bị fixture nền và dữ liệu riêng.
3. Chạy test và thu thập bằng chứng.
4. Giữ lại dữ liệu cần điều tra nếu test thất bại.
5. Dọn dữ liệu thuộc quyền sở hữu của run.
6. Xác minh cleanup thành công.
7. Dọn các tài nguyên hết hạn theo chính sách.

Không nên xóa dữ liệu ngay lập tức nếu nó cần thiết để điều tra lỗi. Có thể giữ lại trong thời hạn ngắn, gắn trạng thái cần điều tra và giới hạn quyền truy cập. Sau thời hạn, cleanup tự động sẽ xóa tài nguyên.

Cleanup phải an toàn khi chạy nhiều lần (idempotent), chỉ tác động đến tài nguyên được gắn nhãn hoặc namespace của run hiện tại và không dựa vào lệnh xóa rộng. Nếu cleanup thất bại, ghi log, cảnh báo và có quy trình dọn tồn đọng.

Có thể gắn metadata như createdByTestRun, owner, expiresAt hoặc tag môi trường cho tài nguyên. Nhờ đó, tác vụ định kỳ có thể tìm và xóa tài nguyên quá hạn theo chính sách.

## 12. Tránh phụ thuộc thứ tự và trạng thái còn sót

Một test suite đáng tin cậy cần có khả năng chạy test riêng lẻ, theo nhóm, theo thứ tự khác nhau và song song mà vẫn giữ kết quả tương đương trong điều kiện giống nhau.

Các thực hành hữu ích:

- Mỗi test tự chuẩn bị dữ liệu đầu vào.
- Không dùng kết quả của test trước làm tiền điều kiện ngầm.
- Không phụ thuộc thứ tự file hoặc thứ tự test runner.
- Dùng dữ liệu riêng hoặc fixture bất biến.
- Dọn trạng thái sau test và kiểm tra cleanup.
- Chạy thử suite theo thứ tự ngẫu nhiên để tìm phụ thuộc ẩn.
- Chạy song song một số nhóm để phát hiện tranh chấp.
- Ghi lại seed và run ID khi thứ tự được xáo trộn.

Khi phát hiện test phụ thuộc thứ tự, không nên chỉ sắp xếp test để che lỗi. Hãy tìm trạng thái dùng chung, dữ liệu chưa được reset, cache hoặc event tồn đọng. Việc chạy tuần tự có thể là giải pháp tạm thời cho tài nguyên không thể cô lập, nhưng phải ghi rõ lý do và kế hoạch xử lý nếu nó trở thành điểm nghẽn.

## 13. Cô lập dữ liệu trong kiểm thử migration và tương thích phiên bản

Migration thường thay đổi schema hoặc chuyển đổi dữ liệu. Nếu nhiều test hoặc môi trường cùng dùng một database, migration có thể làm hỏng trạng thái mà test khác đang cần.

Một chiến lược an toàn:

- Tạo database hoặc schema tạm từ phiên bản nền xác định.
- Nạp dataset có phiên bản và checksum nếu phù hợp.
- Chạy migration trên bản sao.
- Xác minh cấu trúc, ràng buộc và dữ liệu sau chuyển đổi.
- Kiểm tra khả năng ứng dụng phiên bản cũ và mới cùng tồn tại nếu cần.
- Kiểm tra rollback hoặc phương án phục hồi theo thiết kế.
- Xóa database tạm sau khi lưu bằng chứng.

Không chạy migration thử nghiệm trực tiếp trên database production. Với dữ liệu lớn, có thể dùng snapshot hoặc bản sao đã xử lý để giảm thời gian chuẩn bị. Cần ghi nhận khác biệt giữa dataset thử nghiệm và dữ liệu thật, đặc biệt là phân bố, kích thước và quan hệ dữ liệu.

## 14. Ví dụ: cô lập dữ liệu cho test đặt hàng chạy song song

Giả sử CI chạy 40 test đặt hàng trên 4 worker. Mỗi test cần khách hàng, sản phẩm, tồn kho, đơn hàng và sự kiện thanh toán.

Nếu tất cả test dùng chung một khách hàng và một SKU với số lượng tồn kho nhỏ, các worker có thể cùng giảm tồn kho. Một test có thể thất bại vì worker khác đã đặt hết hàng. Nếu cleanup xóa toàn bộ đơn hàng test, nó có thể xóa cả đơn hàng đang được worker khác xác minh.

Một thiết kế cô lập có thể là:

- Mỗi pipeline có run ID riêng.
- Mỗi worker có namespace hoặc tenant riêng.
- Mỗi test tạo customer và order ID duy nhất.
- Product catalog nền được dùng chung ở chế độ chỉ đọc.
- Nếu cần thay đổi tồn kho, mỗi test dùng inventory fixture riêng hoặc bản sao dữ liệu riêng.
- Queue và object storage dùng prefix theo run/worker.
- Payment sandbox dùng account hoặc idempotency key riêng.
- Cleanup chỉ xóa dữ liệu gắn với run ID và worker sở hữu.
- Khi test fail, giữ dữ liệu của test đó trong thời hạn điều tra.

Một ma trận minh họa:

| Tài nguyên | Cách chia sẻ | Cách cô lập |
|---|---|---|
| Product catalog | Dùng chung | Chỉ đọc, fixture có phiên bản |
| Customer | Riêng từng test | ID và email duy nhất |
| Inventory | Riêng theo test hoặc worker | Không để test cùng sửa một số lượng |
| Order | Riêng từng test | Gắn run ID và test ID |
| Payment event | Riêng theo run | Metadata và queue namespace |
| Invoice file | Riêng theo test | Prefix trong object storage |
| Logs và traces | Có thể tập trung | Correlation ID để lọc theo test |
| Cleanup | Theo quyền sở hữu | Chỉ xóa tài nguyên của run hiện tại |

Để xác minh, chạy một tập test theo thứ tự tuần tự, thứ tự ngẫu nhiên và song song. So sánh kết quả và kiểm tra không có bản ghi, event hoặc file của worker này xuất hiện trong kết quả worker khác. Đồng thời thử dừng một worker giữa chừng để xác minh tài nguyên còn sót được nhận diện và dọn theo chính sách.

## 15. Theo dõi chất lượng cô lập và xử lý dữ liệu tồn đọng

Cô lập cần được kiểm tra định kỳ. Một số chỉ số có thể giúp phát hiện vấn đề:

- Tỷ lệ test chỉ pass khi chạy đơn lẻ.
- Số lỗi do xung đột dữ liệu hoặc tài nguyên.
- Số lần cleanup thất bại.
- Số namespace hoặc tài nguyên quá hạn.
- Thời gian tạo và xóa môi trường tạm.
- Tỷ lệ test có dữ liệu hoặc ID cố định.
- Số lần test bị ảnh hưởng bởi thứ tự thực thi.
- Số lần pipeline kết nối sai môi trường hoặc dùng sai secret.
- Chi phí database, storage và runner dành cho dữ liệu thử nghiệm.

Không nên tối ưu cleanup bằng cách xóa quá sớm dữ liệu cần điều tra. Cũng không nên giữ dữ liệu vô thời hạn vì làm tăng chi phí và rủi ro riêng tư. Định nghĩa thời hạn giữ, điều kiện giữ lại khi thất bại, người có quyền gia hạn và cách xóa cuối cùng.

Khi phát hiện rò rỉ dữ liệu giữa test, hãy xác định ranh giới bị vi phạm, phạm vi ảnh hưởng, dữ liệu có nhạy cảm không và có cần điều tra sự cố hay không. Sửa nguyên nhân ở factory, namespace, quyền hoặc cleanup; sau đó thêm kiểm tra hồi quy để bảo vệ ranh giới.

## 16. Quy trình thiết kế và xác minh cô lập dữ liệu

Có thể áp dụng quy trình sau:

1. **Lập bản đồ tài nguyên có trạng thái:** database, queue, file, cache, tài khoản, cấu hình và phụ thuộc ngoài.
2. **Xác định chủ sở hữu và phạm vi chia sẻ:** test case, worker, test run, nhóm hoặc môi trường.
3. **Chọn chiến lược cô lập:** dữ liệu riêng, transaction, schema, tenant, namespace, fixture bất biến hoặc môi trường tạm.
4. **Thiết kế định danh:** tạo run ID, worker ID và test ID để truy vết tài nguyên.
5. **Chuẩn bị dữ liệu và quyền:** factory, fixture, secret và tài khoản riêng.
6. **Định nghĩa vòng đời:** tạo, sử dụng, giữ để điều tra, cleanup và hết hạn.
7. **Chạy kiểm tra độc lập và song song:** thử thứ tự khác nhau, nhiều worker và tình huống dừng giữa chừng.
8. **Xác minh ranh giới:** đảm bảo test chỉ đọc/ghi dữ liệu thuộc phạm vi của mình.
9. **Theo dõi tồn đọng và cải tiến:** đo cleanup, xung đột, thời gian cấp phát và chi phí.

~~~mermaid
flowchart TD
    A["Liệt kê dữ liệu và tài nguyên có trạng thái"] --> B["Xác định ranh giới và chủ sở hữu"]
    B --> C["Chọn chiến lược cô lập phù hợp"]
    C --> D["Tạo run ID, worker ID và test ID"]
    D --> E["Chuẩn bị fixture, quyền và môi trường"]
    E --> F["Chạy test độc lập và song song"]
    F --> G["Xác minh không có truy cập chéo"]
    G --> H{"Cô lập đạt yêu cầu?"}
    H -->|Không| I["Sửa namespace, quyền, dữ liệu hoặc cleanup"]
    I --> C
    H -->|Có| J["Lưu bằng chứng và dọn theo vòng đời"]
    J --> K["Theo dõi tồn đọng và cải tiến"]
~~~

## 17. Checklist cô lập dữ liệu

Trước khi đưa bộ kiểm thử vào CI hoặc mở rộng chạy song song, hãy kiểm tra:

- Đã liệt kê mọi tài nguyên có trạng thái mà test có thể đọc hoặc thay đổi chưa?
- Mỗi test có tự chuẩn bị dữ liệu và không phụ thuộc test khác không?
- Dữ liệu dùng chung có bất biến hoặc chỉ đọc không?
- ID, email, file, event và key cache có đủ duy nhất không?
- Worker và test run có namespace hoặc ranh giới sở hữu rõ không?
- Transaction rollback có bao phủ đúng thao tác và side effect không?
- Queue, object storage, cache và sandbox có được cô lập không?
- Local, CI, staging và production có dữ liệu, secret và quyền tách biệt không?
- Dataset có thể tạo lại, có phiên bản và đủ đại diện không?
- Cleanup có an toàn khi chạy nhiều lần và chỉ xóa tài nguyên thuộc quyền sở hữu không?
- Dữ liệu lỗi có được giữ lại đủ lâu để điều tra theo chính sách không?
- Có thể chạy test theo thứ tự ngẫu nhiên và song song mà không thay đổi kết quả không?
- Có cơ chế phát hiện và dọn tài nguyên tồn đọng không?
- Bằng chứng có gắn với run ID, worker ID, phiên bản và môi trường không?

Cô lập dữ liệu giữa ca, nhóm thực thi và môi trường là nền tảng để kiểm thử có thể lặp lại và mở rộng. Khi mỗi test có quyền sở hữu dữ liệu rõ, tài nguyên dùng chung được kiểm soát, môi trường được tách biệt và cleanup tuân theo vòng đời, nhóm giảm được lỗi do tranh chấp trạng thái và tránh rò rỉ dữ liệu giữa các lần chạy. Thiết kế cô lập nên bắt đầu từ ranh giới kiến trúc và rủi ro thực tế, sau đó được xác minh bằng chạy độc lập, chạy song song và kiểm tra quyền truy cập.

