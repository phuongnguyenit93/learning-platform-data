# Quản lý dữ liệu kiểm thử và trạng thái ban đầu

## Mục tiêu học tập

Sau bài này, người học có thể:

- Giải thích vì sao kết quả kiểm thử phụ thuộc vào cả mã nguồn, dữ liệu và trạng thái của hệ thống.
- Phân biệt fixture, seed data, test data factory, snapshot và dữ liệu sinh trong lúc chạy test.
- Thiết kế trạng thái ban đầu có thể tái tạo cho unit test, integration test và end-to-end test.
- Cô lập dữ liệu giữa test, job, nhánh và môi trường để tránh ghi đè hoặc phụ thuộc thứ tự chạy.
- Chọn dữ liệu tổng hợp, dữ liệu giả lập hoặc dữ liệu đã ẩn danh theo yêu cầu bảo mật.
- Quản lý vòng đời dữ liệu từ khởi tạo, sử dụng, xác minh đến dọn dẹp.
- Tích hợp việc chuẩn bị và khôi phục trạng thái vào pipeline CI/CD để kết quả ổn định và có thể điều tra.

## 1. Vì sao dữ liệu và trạng thái ban đầu quan trọng?

Một bài kiểm thử không chỉ kiểm tra mã nguồn. Nó kiểm tra hành vi của phần mềm khi nhận đầu vào và tương tác với trạng thái hiện tại của hệ thống.

Cùng một commit có thể cho kết quả khác nhau nếu:

- Cơ sở dữ liệu chứa dữ liệu khác nhau.
- Một test phụ thuộc vào bản ghi do test trước tạo ra.
- Hàng đợi còn message từ lần chạy cũ.
- Cache chứa giá trị cũ.
- Feature flag hoặc cấu hình môi trường đã bị thay đổi.
- Tài khoản kiểm thử đã bị khóa hoặc hết hạn.
- Đồng hồ hệ thống, múi giờ hoặc dữ liệu thời gian không được cố định.
- Một pipeline khác đang cập nhật cùng tài nguyên trong lúc test chạy.

Vì vậy, một kết quả test chỉ có ý nghĩa khi biết được **mã nào đã được kiểm tra, dữ liệu nào được dùng và hệ thống bắt đầu từ trạng thái nào**.

Quản lý dữ liệu kiểm thử là việc chuẩn bị, cấp phát, bảo vệ, theo dõi và dọn dẹp dữ liệu phục vụ kiểm thử. Quản lý trạng thái ban đầu còn rộng hơn: nó xác định những điều kiện mà hệ thống phải có trước khi test bắt đầu, bao gồm dữ liệu, cấu hình, trạng thái dịch vụ phụ thuộc và các tài nguyên có thể thay đổi.

Có thể hình dung:

> Kết quả kiểm thử đáng tin cậy cần có đầu vào xác định, trạng thái ban đầu xác định, hành vi có thể quan sát và cách kết thúc có kiểm soát.

Nếu không quản lý được những yếu tố này, test có thể thất bại ngẫu nhiên, thành công giả hoặc chỉ chạy đúng trên một môi trường cụ thể.

## 2. Phân biệt dữ liệu kiểm thử và trạng thái ban đầu

Hai khái niệm này liên quan nhưng không giống nhau.

**Dữ liệu kiểm thử (test data)** là các giá trị và bản ghi được test đọc, tạo, sửa hoặc xóa. Ví dụ: tài khoản khách hàng, sản phẩm, đơn hàng, quyền người dùng, bản ghi thanh toán giả lập hoặc message trong queue.

**Trạng thái ban đầu (initial state / baseline state)** là trạng thái tổng thể của các thành phần liên quan trước khi test bắt đầu. Nó có thể bao gồm:

- Dữ liệu trong database.
- Nội dung cache.
- Message trong queue hoặc event log.
- File trong storage.
- Trạng thái tài khoản và phiên đăng nhập.
- Feature flags và cấu hình.
- Phiên bản schema và migration.
- Trạng thái dịch vụ giả lập hoặc sandbox bên ngoài.
- Thời gian hệ thống, múi giờ và dữ liệu tham chiếu.

Ví dụ, test chức năng đặt hàng có thể cần một khách hàng đang hoạt động, một sản phẩm còn hàng, một phương thức thanh toán sandbox và một giỏ hàng chưa được checkout. Chỉ tạo bản ghi khách hàng là chưa đủ nếu sản phẩm đã hết hàng hoặc payment sandbox đang ở trạng thái lỗi.

| Khía cạnh | Dữ liệu kiểm thử | Trạng thái ban đầu |
|---|---|---|
| Phạm vi | Bản ghi và giá trị test sử dụng | Toàn bộ điều kiện cần cho test |
| Ví dụ | Customer, product, order | Customer active, stock đủ, queue sạch |
| Cách chuẩn bị | Fixture, seed, factory, API | Reset, migration, config, service setup |
| Cách xác minh | Truy vấn hoặc API kiểm tra bản ghi | Health check và assertion trạng thái |
| Cách khôi phục | Xóa hoặc cập nhật dữ liệu test | Reset hoặc tái tạo baseline |

Một bộ dữ liệu có thể đúng nhưng baseline vẫn sai. Ví dụ test tạo đúng đơn hàng nhưng queue còn event cũ khiến consumer xử lý nhầm. Ngược lại, môi trường có baseline sạch nhưng thiếu dữ liệu cần thiết để kiểm tra luồng nghiệp vụ.

## 3. Các cách tạo và quản lý dữ liệu kiểm thử

Không có một kỹ thuật duy nhất phù hợp cho mọi loại test. Cần chọn phương pháp theo tốc độ, độ cô lập, mức độ thực tế và chi phí chuẩn bị.

### 3.1. Fixture

Fixture là tập dữ liệu hoặc trạng thái được chuẩn bị trước để một test hoặc nhóm test sử dụng.

Ví dụ fixture có thể chứa:

- Một khách hàng đang hoạt động.
- Một sản phẩm có tồn kho.
- Một đơn hàng ở trạng thái pending.
- Một tài khoản có vai trò cụ thể.
- Một response mẫu từ dịch vụ bên ngoài.

Fixture phù hợp khi dữ liệu nhỏ, ổn định và dễ hiểu. Nó giúp test tập trung vào hành vi cần kiểm tra thay vì phải tạo lại nhiều đối tượng liên quan.

Nhược điểm xuất hiện khi fixture quá lớn hoặc dùng chung cho nhiều test. Khi một test sửa fixture, test khác có thể nhận trạng thái đã bị thay đổi. Fixture khó bảo trì cũng có thể che giấu những quan hệ dữ liệu không còn đúng với mô hình hiện tại.

Nên giữ fixture tối thiểu, đặt tên theo mục đích và tạo bản riêng cho test có khả năng sửa dữ liệu.

### 3.2. Seed data

Seed data là dữ liệu nền được nạp vào môi trường để ứng dụng hoặc test có thể hoạt động.

Ví dụ:

- Danh mục quốc gia và đơn vị tiền tệ.
- Vai trò và quyền mặc định.
- Loại sản phẩm chuẩn.
- Các mã trạng thái hoặc cấu hình tham chiếu.
- Dữ liệu tối thiểu cần cho môi trường demo hoặc kiểm thử tích hợp.

Seed data thường tồn tại lâu hơn một test đơn lẻ. Vì vậy, cần xác định rõ seed nào là dữ liệu hệ thống và seed nào là dữ liệu riêng của test.

Seed nên có tính lặp an toàn (idempotent): chạy lại không tạo ra bản ghi trùng hoặc làm thay đổi ngoài ý muốn. Có thể dùng khóa tự nhiên hoặc mã định danh cố định để nhận diện bản ghi. Tránh dùng một script seed có hành vi xóa toàn bộ dữ liệu nếu nó có thể được gọi nhầm ở môi trường không phải test.

### 3.3. Test data factory

Factory tạo dữ liệu theo nhu cầu của từng test. Test khai báo những thuộc tính quan trọng, còn factory cung cấp các giá trị hợp lệ mặc định.

Ví dụ, factory tạo một customer mới với email duy nhất và trạng thái active. Test có thể ghi đè thuộc tính để kiểm tra trường hợp bị khóa, thiếu địa chỉ hoặc có lịch sử giao dịch.

Factory phù hợp khi:

- Mỗi test cần một đối tượng riêng.
- Dữ liệu có nhiều quan hệ.
- Cần tạo nhanh các biến thể hợp lệ và không hợp lệ.
- Test chạy song song và không nên dùng chung ID.

Factory cần tạo dữ liệu có ý nghĩa và giữ các invariant nghiệp vụ. Không nên tạo những bản ghi không thể tồn tại trong hệ thống thật, trừ khi test đang cố ý kiểm tra dữ liệu lỗi ở ranh giới phù hợp.

### 3.4. Dữ liệu sinh trong lúc chạy

Một số test tạo dữ liệu trực tiếp qua API hoặc repository ngay trước khi thực hiện hành động cần kiểm tra. Cách này giúp test tự mô tả và giảm phụ thuộc vào bộ dữ liệu dùng chung.

Ví dụ:

1. Tạo một customer qua API test.
2. Tạo một product có stock bằng một giá trị xác định.
3. Gửi yêu cầu tạo order.
4. Kiểm tra trạng thái order và số lượng stock.
5. Xóa dữ liệu hoặc hủy tài nguyên test.

Dữ liệu sinh trong lúc chạy phù hợp với integration test và end-to-end test, nhưng cần kiểm soát thời gian tạo, quan hệ phụ thuộc và cleanup. Nếu việc tạo dữ liệu quá phức tạp, có thể chuyển phần setup chung vào helper hoặc factory để test vẫn dễ đọc.

### 3.5. Snapshot hoặc bản sao môi trường

Snapshot là ảnh chụp trạng thái tại một thời điểm. Có thể dùng snapshot database hoặc volume để khởi tạo nhanh môi trường kiểm thử có dữ liệu tương đối lớn.

Cách này hữu ích khi:

- Bộ dữ liệu có cấu trúc phức tạp.
- Seed từ đầu quá chậm.
- Cần kiểm thử migration trên trạng thái gần với một phiên bản schema cụ thể.
- Cần tái tạo một lỗi phụ thuộc vào trạng thái dữ liệu.

Snapshot phải có phiên bản, nguồn gốc và chính sách bảo vệ rõ ràng. Nếu snapshot chứa dữ liệu production, nó có thể chứa thông tin cá nhân hoặc bí mật. Cần ẩn danh trước khi dùng, giới hạn quyền truy cập và thời gian lưu giữ. Snapshot cũng có thể trở nên lỗi thời khi schema hoặc seed thay đổi.

## 4. Chọn dữ liệu theo loại kiểm thử

Các tầng kiểm thử có nhu cầu dữ liệu và baseline khác nhau.

| Loại test | Dữ liệu phù hợp | Baseline nên kiểm soát |
|---|---|---|
| Unit test | Đối tượng nhỏ, fixture trong bộ nhớ, factory | Trạng thái đối tượng và thời gian được cố định |
| Component test | Database hoặc service giả lập cục bộ | Schema, seed tối thiểu, mock/stub state |
| Integration test | Bản ghi và service thực trong môi trường cô lập | Database, queue, cache, dependency version |
| Contract test | Request/response mẫu và schema | Phiên bản contract, provider/consumer expectation |
| End-to-end test | Dữ liệu nghiệp vụ gần thực tế | Toàn bộ luồng, tài khoản, feature flag, trạng thái bên ngoài |
| Performance test | Dataset đủ lớn và phân bố gần tải thực tế | Kích thước dữ liệu, cache state, concurrency, tài nguyên |
| Migration test | Snapshot hoặc dữ liệu đại diện trước migration | Schema nguồn, version ứng dụng và backup |

Không nên dùng cùng một bộ dữ liệu khổng lồ cho mọi test. Unit test cần nhanh và tập trung. Performance test cần dữ liệu đủ lớn và có phân bố hợp lý. End-to-end test cần dữ liệu nghiệp vụ dễ truy vết nhưng phải được cô lập để không ảnh hưởng người khác.

Cũng không nên dùng mock thay thế cho mọi dependency. Mock giúp kiểm soát đầu vào và lỗi ở unit/component test, nhưng không chứng minh tích hợp thật hoạt động. Những tương tác quan trọng với database, queue hoặc API cần có test phù hợp trên thành phần thực hoặc môi trường tương đương.

## 5. Thiết kế baseline có thể tái tạo

Một baseline tốt cần có định nghĩa rõ, cách tạo và cách xác minh.

### 5.1. Xác định invariant

Invariant là điều kiện phải đúng trước khi test bắt đầu.

Ví dụ cho luồng checkout:

- Customer tồn tại và đang active.
- Product tồn tại và có stock đủ.
- Cart thuộc đúng customer và chưa checkout.
- Payment provider đang ở sandbox mode.
- Queue không còn event của lần test trước trong phạm vi đang dùng.
- Feature flag checkout đang bật.
- Database schema ở phiên bản mà test mong đợi.

Nên ghi invariant dưới dạng kiểm tra có thể tự động hóa, thay vì chỉ ghi trong tài liệu hướng dẫn.

### 5.2. Tạo baseline từ mã hoặc dữ liệu có phiên bản

Cấu hình tạo schema, seed và fixture nên được lưu trong repository hoặc một nguồn được quản trị. Mỗi lần thay đổi baseline cần review như thay đổi mã nguồn.

Có thể ghi metadata:

- Phiên bản schema hoặc migration.
- Phiên bản bộ seed.
- Mã commit của test suite.
- Phiên bản image database hoặc service.
- Cấu hình môi trường.
- Dataset ID hoặc snapshot version.

Metadata này giúp xác định hai lần test có bắt đầu từ cùng điều kiện hay không.

### 5.3. Kiểm tra baseline trước khi chạy test

Sau khi setup, chạy một bước readiness check để xác nhận:

- Database kết nối được và ở đúng schema version.
- Seed data cần thiết đã tồn tại.
- Queue hoặc topic đã được tạo đúng.
- Service phụ thuộc ở trạng thái sẵn sàng.
- Tài khoản test có quyền đúng.
- Feature flag và cấu hình nằm trong giá trị dự kiến.

Nếu baseline không đạt, test nên dừng ở bước setup với thông báo rõ. Không nên tiếp tục chạy hàng trăm test rồi báo lỗi ở nhiều nơi do cùng một nguyên nhân chuẩn bị môi trường.

## 6. Cô lập dữ liệu giữa các test và pipeline

Một trong những nguyên nhân phổ biến của flaky test là nhiều test hoặc pipeline cùng thao tác trên dữ liệu chung.

Ví dụ hai test cùng sử dụng customer ID 1001. Test A đổi trạng thái customer thành inactive, trong khi test B đang kiểm tra checkout. Kết quả của test B phụ thuộc vào thời điểm hai test chạy.

Có một số chiến lược cô lập:

### 6.1. Dữ liệu riêng cho từng test

Mỗi test tạo đối tượng với ID riêng, chẳng hạn UUID hoặc mã định danh có namespace. Test chỉ đọc và sửa dữ liệu do chính nó tạo.

Cách này phù hợp khi số lượng bản ghi nhỏ và hệ thống hỗ trợ tạo dữ liệu nhanh.

### 6.2. Schema hoặc database riêng cho từng job

Mỗi job CI được cấp một schema hoặc database độc lập. Các test không ghi vào vùng dữ liệu của job khác.

Cách này phù hợp với integration test có nhiều thao tác database. Cần quản lý quota, tên schema, quyền và cleanup sau khi job kết thúc.

### 6.3. Tenant hoặc namespace riêng

Với ứng dụng multi-tenant, mỗi test có thể dùng tenant riêng. Với hệ thống dùng Kubernetes hoặc service có namespace, có thể tạo namespace theo run ID hoặc pull request.

Tuy nhiên, namespace ứng dụng không tự động cô lập database, queue, object storage hoặc dịch vụ bên ngoài. Cần kiểm tra từng dependency và cấp vùng dữ liệu riêng tương ứng.

### 6.4. Transaction rollback

Một test có thể chạy trong transaction và rollback sau khi hoàn tất. Cách này nhanh và hữu ích với test database đơn giản.

Nhưng transaction rollback không giải quyết mọi loại trạng thái:

- Một số thao tác ghi ra message queue không nằm trong transaction database.
- Gọi API bên ngoài không thể tự động rollback.
- Một số test cần nhiều connection hoặc tiến trình khác đọc dữ liệu đã commit.
- DDL hoặc hành vi transaction khác nhau giữa các database.
- Test kiểm tra transaction commit hoặc isolation không thể bị bao toàn bộ trong transaction của test harness.

Do đó, cần chọn transaction rollback cho phạm vi phù hợp và có cơ chế cleanup riêng cho tài nguyên ngoài transaction.

### 6.5. Môi trường tạm thời

Với test tích hợp lớn, có thể tạo môi trường ephemeral cho mỗi pull request hoặc pipeline. Môi trường có vòng đời từ tạo, triển khai, seed, chạy test đến hủy.

Cách này giảm xung đột giữa nhánh và cho phép chạy song song, nhưng cần kiểm soát chi phí, quota, thời gian tạo và dọn dẹp tài nguyên.

## 7. Dữ liệu phải độc lập với thứ tự chạy test

Một bộ test ổn định phải cho kết quả giống nhau khi test được chạy riêng lẻ, theo nhóm hoặc theo thứ tự khác nhau.

Dấu hiệu test phụ thuộc thứ tự:

- Test B chỉ chạy được sau Test A.
- Test chạy lại lần hai thì thất bại vì dữ liệu đã tồn tại.
- Test chỉ thành công khi chạy tuần tự.
- Test thất bại ngẫu nhiên khi bật parallel execution.
- Test dùng chung một biến static hoặc một record trong database.

Để giảm phụ thuộc thứ tự:

1. Mỗi test tự chuẩn bị dữ liệu cần thiết.
2. Không dựa vào side effect của test khác.
3. Dùng ID duy nhất hoặc namespace theo test.
4. Không dùng dữ liệu mutable toàn cục nếu không có cơ chế reset.
5. Cleanup trong finally hoặc lifecycle hook phù hợp.
6. Có thể chạy test theo thứ tự ngẫu nhiên trong một số lượt kiểm tra.
7. Chạy song song có kiểm soát để phát hiện tài nguyên dùng chung.

Test chạy độc lập giúp việc retry và điều tra lỗi đơn giản hơn. Nếu một test chỉ có thể chạy trong một chuỗi dài, cần xem lại ranh giới setup và dữ liệu mà nó phụ thuộc.

## 8. Dữ liệu tổng hợp, dữ liệu giả lập và dữ liệu ẩn danh

Dữ liệu production có thể phản ánh chính xác phân bố và quan hệ nghiệp vụ, nhưng thường chứa thông tin cá nhân, bí mật hoặc dữ liệu nhạy cảm. Không nên sao chép nguyên trạng dữ liệu production vào CI hoặc môi trường phát triển.

Có ba lựa chọn phổ biến:

**Synthetic data (dữ liệu tổng hợp):** được tạo nhân tạo theo schema và phân bố mong muốn. Ví dụ tạo hàng nghìn customer với độ tuổi, địa chỉ, đơn hàng và trạng thái đa dạng. Dữ liệu tổng hợp giúp kiểm soát nội dung và tránh sử dụng thông tin thật.

**Mocked/fake data (dữ liệu giả lập):** được tạo để mô phỏng một tình huống hoặc phản hồi cụ thể. Ví dụ payment provider trả về thành công, từ chối hoặc timeout. Dữ liệu giả lập hữu ích cho test các nhánh lỗi và tình huống khó tái tạo.

**Masked/anonymized data (dữ liệu đã che/ẩn danh):** dữ liệu lấy từ nguồn thật nhưng các trường nhận diện được biến đổi hoặc loại bỏ theo chính sách. Cần đánh giá nguy cơ tái nhận diện và bảo toàn quan hệ dữ liệu. Chỉ đổi tên hoặc email là chưa chắc đã đủ ẩn danh.

| Phương pháp | Ưu điểm | Giới hạn |
|---|---|---|
| Synthetic | Kiểm soát nội dung, an toàn hơn cho dữ liệu nhạy cảm | Có thể không phản ánh hết phân bố thực tế |
| Mock/fake | Tái tạo lỗi và phản hồi cụ thể, nhanh | Có thể không phản ánh hành vi tích hợp thật |
| Masked/anonymized | Giữ được một phần cấu trúc và phân bố thực tế | Có nguy cơ tái nhận diện nếu xử lý không đúng |

Cần có quy trình phê duyệt nguồn dữ liệu, quyền truy cập, masking, kiểm tra và thời gian lưu giữ. Không đưa dữ liệu production hoặc bản sao snapshot chưa được bảo vệ vào cache dùng chung, log hoặc artifact công khai.

## 9. Quản lý thời gian, số ngẫu nhiên và dữ liệu biến đổi

Một số test không ổn định vì phụ thuộc vào thời gian hiện tại hoặc dữ liệu ngẫu nhiên.

Ví dụ:

- Test kiểm tra subscription hết hạn nhưng dùng thời gian thực.
- Test tạo email ngẫu nhiên nhưng không lưu lại giá trị để kiểm tra.
- Test dùng ngày theo múi giờ local của runner.
- Test so sánh timestamp với độ chính xác khác nhau giữa hệ thống.

Các biện pháp:

- Tiêm clock hoặc time provider để test cố định thời gian.
- Dùng UTC cho dữ liệu thời gian lưu trữ và chuyển múi giờ ở ranh giới hiển thị.
- Cố định seed của random generator khi cần tái tạo lỗi.
- Ghi lại seed hoặc dữ liệu sinh ra trong log test.
- Dùng tolerance phù hợp khi so sánh thời gian hoặc số thực.
- Tránh phụ thuộc vào thời điểm chạy của runner.

Không phải lúc nào cũng nên dùng cùng một seed cho mọi test. Seed cố định giúp tái tạo lỗi, nhưng một số test property-based nên chạy nhiều seed để khám phá đầu vào. Khi thất bại, cần ghi seed để có thể chạy lại đúng trường hợp.

## 10. Cleanup và khôi phục trạng thái sau test

Chuẩn bị dữ liệu chỉ là một nửa của vòng đời. Test cần kết thúc trong trạng thái không ảnh hưởng đến lần chạy sau.

Một chiến lược cleanup nên xác định:

- Dữ liệu nào test sở hữu.
- Tài nguyên nào được phép xóa.
- Cleanup chạy sau từng test, từng suite hay khi hủy môi trường.
- Cách xử lý nếu test bị timeout hoặc runner bị kill.
- Cách phát hiện và dọn tài nguyên mồ côi.

Không nên xóa dữ liệu chỉ dựa vào một điều kiện quá rộng như “xóa mọi bản ghi tạo hôm nay”. Hãy gắn dữ liệu với test run ID hoặc tenant riêng, rồi chỉ dọn tài nguyên thuộc phạm vi đó.

Có thể dùng TTL hoặc janitor job để dọn môi trường tạm thời và dữ liệu bị bỏ lại. Janitor cần kiểm tra owner, thời điểm hết hạn và trạng thái tài nguyên trước khi xóa.

Một số test cố ý kiểm tra dữ liệu sau khi xử lý, vì vậy cleanup cần diễn ra sau khi assertion hoàn tất. Với test bất đồng bộ, cần đợi consumer xử lý hoặc xác minh trạng thái cuối trước khi xóa dữ liệu liên quan.

Nếu cleanup thất bại, cần ghi lại tài nguyên còn tồn tại và cảnh báo owner. Không nên âm thầm bỏ qua vì dữ liệu mồ côi có thể gây nhiễu test hoặc tăng chi phí.

## 11. Ví dụ vòng đời dữ liệu kiểm thử trong CI

Một pipeline integration test có thể triển khai theo luồng:

~~~mermaid
flowchart TD
    A["Start CI job"] --> B["Tạo test namespace / database"]
    B --> C["Apply schema migrations"]
    C --> D["Load versioned seed data"]
    D --> E["Readiness checks"]
    E --> F{"Baseline hợp lệ?"}
    F -- "Không" --> X["Fail setup và ghi chẩn đoán"]
    F -- "Có" --> G["Tạo dữ liệu riêng cho test"]
    G --> H["Chạy integration tests"]
    H --> I["Thu thập report và log"]
    I --> J["Cleanup dữ liệu và tài nguyên"]
    J --> K["Ghi nhận kết quả CI"]
    X --> J
~~~

Một ví dụ cấu hình logic tổng quát:

~~~yaml
integration_test:
  environment:
    isolation_key: ci_run_id
    database: ephemeral
    queue_namespace: ci_run_id
    external_services: sandbox

  setup:
    - create_resources
    - apply_migrations
    - load_versioned_seed
    - verify_baseline

  test:
    - create_test_data_per_case
    - run_integration_suite
    - collect_reports

  cleanup:
    always:
      - delete_test_data_by_owner
      - destroy_ephemeral_resources
      - record_cleanup_result
~~~

Ví dụ chỉ mô tả thứ tự và trách nhiệm. Cú pháp triển khai cần được ánh xạ sang nền tảng CI và công cụ test của dự án. Đặc biệt, cleanup cần được cấu hình để chạy cả khi test thất bại hoặc bị hủy theo khả năng của runner.

## 12. Ví dụ Java: setup và cleanup dữ liệu trong integration test

Một test tích hợp cần tạo dữ liệu riêng, thực hiện hành động và xác minh kết quả. Ví dụ dưới đây minh họa ý tưởng bằng JUnit và repository giả định:

~~~java
class OrderServiceIT {
    private final OrderRepository orders;
    private final CustomerRepository customers;
    private final OrderService orderService;

    @Test
    void createsOrderForActiveCustomer() {
        String runId = UUID.randomUUID().toString();
        String email = "ci-" + runId + "@example.test";

        Customer customer = customers.save(
            new Customer(email, CustomerStatus.ACTIVE)
        );

        try {
            Order order = orderService.createOrder(customer.getId());

            assertEquals(customer.getId(), order.getCustomerId());
            assertEquals(OrderStatus.PENDING, order.getStatus());
        } finally {
            orders.deleteByCustomerId(customer.getId());
            customers.deleteById(customer.getId());
        }
    }
}
~~~

Điểm cần chú ý:

- Dữ liệu được tạo trong test và có định danh riêng.
- Email có run ID để giảm xung đột khi chạy song song.
- Assertion kiểm tra hành vi nghiệp vụ.
- Cleanup chỉ xóa dữ liệu thuộc test vừa tạo.

Đây là ví dụ khái niệm. Trong dự án thực tế, có thể dùng transaction, test fixture, repository helper hoặc container database. Nếu service phát sinh event hoặc gọi hệ thống ngoài, cần cleanup hoặc reset những trạng thái đó riêng; xóa bản ghi database không tự thu hồi message đã publish.

## 13. Kiểm thử migration trên dữ liệu có trạng thái

Migration test cần xác minh nhiều hơn việc câu lệnh SQL chạy không lỗi. Nó cần xác nhận dữ liệu cũ được chuyển đúng và ứng dụng tương thích với schema mới.

Một quy trình migration test có thể là:

1. Tạo database từ schema phiên bản cũ.
2. Nạp dataset đại diện, gồm dữ liệu biên và quan hệ quan trọng.
3. Ghi lại các invariant trước migration.
4. Chạy migration bằng đúng công cụ sẽ dùng trong pipeline phát hành.
5. Kiểm tra schema mới và dữ liệu sau chuyển đổi.
6. Chạy test tương thích với phiên bản ứng dụng mới.
7. Xác minh các trường hợp lỗi hoặc dữ liệu không hợp lệ.
8. Ghi thời gian thực thi và ảnh hưởng đến khóa hoặc tài nguyên.
9. Hủy database test.

Dataset migration nên bao gồm dữ liệu rỗng, dữ liệu lớn, giá trị null, bản ghi trùng nếu schema cũ cho phép và các quan hệ khóa ngoại quan trọng. Một dataset chỉ có một vài bản ghi sạch có thể bỏ sót lỗi xảy ra trong dữ liệu thật.

Với migration phá hủy hoặc chuyển đổi lớn, cần kiểm tra chiến lược backup/restore và khả năng tương thích giữa phiên bản ứng dụng cũ và mới. Không nên giả định rollback migration luôn đảo ngược chính xác mọi thay đổi dữ liệu.

## 14. Tích hợp quản lý dữ liệu vào CI/CD

Một pipeline tốt cần xem setup và cleanup là phần chính thức của test job, không phải thao tác thủ công ngoài quy trình.

| Giai đoạn | Việc cần làm | Điều kiện chuyển tiếp |
|---|---|---|
| Provision | Tạo database, namespace, queue hoặc service test | Tài nguyên được cấp riêng và sẵn sàng |
| Initialize | Apply migration và seed có phiên bản | Baseline đạt invariant |
| Execute | Tạo dữ liệu theo test và chạy suite | Test hoàn tất hoặc timeout |
| Observe | Thu log, report, trạng thái tài nguyên | Bằng chứng gắn với run ID |
| Cleanup | Xóa dữ liệu và tài nguyên thuộc job | Cleanup được xác nhận hoặc báo lỗi |
| Publish result | Lưu test report và metadata | Có thể truy vết lại môi trường và dataset |

Một số thực hành hữu ích:

- Tạo môi trường bằng IaC hoặc container để cấu hình có thể review.
- Dùng database image có phiên bản cố định.
- Apply migration giống quy trình thực tế.
- Dùng seed versioned và deterministic.
- Tạo dữ liệu riêng theo job hoặc test case.
- Giới hạn quyền của test job vào tài nguyên của chính nó.
- Đặt timeout cho setup, test và cleanup.
- Luôn thu thập report ngay cả khi test thất bại.
- Ghi run ID, commit, image version, schema version và dataset version.
- Có job dọn tài nguyên mồ côi khi cleanup trong runner không hoàn tất.

Không nên cho integration test truy cập production database. Nếu cần dữ liệu có cấu trúc gần thực tế, hãy dùng bản đã được xử lý và nạp vào môi trường test được cô lập.

## 15. Những lỗi thường gặp và cách xử lý

| Dấu hiệu | Nguyên nhân có thể | Cách cải thiện |
|---|---|---|
| Test chạy riêng thì đạt, chạy cả suite thì thất bại | Dữ liệu hoặc trạng thái dùng chung | Setup riêng, reset và cleanup theo test |
| Test chỉ thất bại khi chạy song song | Trùng ID, tenant hoặc tài nguyên | Namespace theo job, concurrency control |
| Chạy lại test bị lỗi duplicate key | Seed hoặc setup không idempotent | Dùng khóa ổn định và upsert có kiểm soát |
| Test pass trên local nhưng fail trên CI | Baseline, timezone hoặc service khác nhau | Chuẩn hóa image, config, clock và seed |
| Integration test lúc nhanh lúc chậm | Dataset hoặc tài nguyên dùng chung thay đổi | Cô lập dữ liệu và theo dõi tài nguyên |
| Queue làm test nhận nhầm event | Message cũ hoặc consumer chạy nền | Queue riêng, correlation ID và cleanup |
| Cleanup không chạy khi job bị hủy | Không có finally/always cleanup hoặc janitor | Dùng cleanup hook và TTL |
| Snapshot có dữ liệu nhạy cảm | Sao chép production thiếu kiểm soát | Mask/anonymize hoặc dùng synthetic data |
| Migration test chỉ dùng database rỗng | Dataset không đại diện | Thêm dữ liệu biên và quan hệ thực tế |
| Test phụ thuộc thời gian hiện tại | Clock không được kiểm soát | Inject clock và cố định timezone |
| Test phụ thuộc thứ tự | Side effect không được reset | Test độc lập và chạy ngẫu nhiên |
| Tài nguyên test tăng dần | Cleanup không đầy đủ | Gắn owner/run ID và janitor job |

## 16. Checklist thiết kế dữ liệu và trạng thái kiểm thử

Trước khi đưa một test suite vào CI, hãy kiểm tra:

- [ ] Đã xác định dữ liệu và trạng thái mà mỗi loại test cần.
- [ ] Baseline có thể tạo lại từ cấu hình hoặc dữ liệu có phiên bản.
- [ ] Có readiness check xác nhận schema, seed và service dependency.
- [ ] Fixture nhỏ, rõ mục đích và không bị sửa dùng chung ngoài ý muốn.
- [ ] Factory tạo dữ liệu hợp lệ và có ID riêng.
- [ ] Test không phụ thuộc dữ liệu do test khác tạo.
- [ ] Dữ liệu được cô lập giữa job, nhánh và môi trường khi cần.
- [ ] Transaction rollback chỉ dùng cho trạng thái nằm trong transaction.
- [ ] Queue, cache, storage và dịch vụ ngoài có chiến lược reset riêng.
- [ ] Dữ liệu nhạy cảm được tổng hợp hoặc ẩn danh theo chính sách.
- [ ] Clock, timezone và random seed được kiểm soát khi ảnh hưởng kết quả.
- [ ] Cleanup chạy khi thành công, thất bại hoặc hủy job.
- [ ] Có TTL hoặc janitor để dọn tài nguyên mồ côi.
- [ ] Test report gắn với commit, run ID, schema và dataset version.
- [ ] Migration được kiểm tra trên dữ liệu đại diện.
- [ ] Không có đường truy cập từ test job đến dữ liệu production.

## 17. Bài tập tự đánh giá

Một nhóm phát triển có integration test cho chức năng đặt hàng. Test dùng chung một database staging. Mỗi lần chạy đều tạo customer có email cố định, tạo order và thêm message vào một queue chung. Khi chạy nhiều pipeline cùng lúc, test đôi khi đọc nhầm order hoặc nhận message từ lần chạy trước. Một số lần test thất bại, dữ liệu vẫn còn trong database.

Hãy đề xuất thiết kế mới:

1. Những thành phần nào thuộc test data và những thành phần nào thuộc baseline state?
2. Nên dùng fixture, seed, factory hay snapshot cho từng loại dữ liệu?
3. Cách nào để cô lập customer, order và message giữa các pipeline?
4. Có thể dùng transaction rollback cho toàn bộ luồng không? Vì sao?
5. Cần kiểm tra baseline nào trước khi bắt đầu test?
6. Cleanup nên chạy ở những thời điểm nào và xử lý ra sao nếu runner bị kill?
7. Làm thế nào để truy vết một message về đúng test run?
8. Dữ liệu nào nên được tổng hợp hoặc ẩn danh?
9. Cần lưu metadata nào để tái tạo một lần test thất bại?

Một thiết kế tốt cần đảm bảo mỗi lần chạy có dữ liệu và phạm vi trạng thái riêng, baseline được xác minh trước test, cleanup có thể theo dõi và lỗi có đủ thông tin để tái tạo.

## Kết luận

Dữ liệu kiểm thử và trạng thái ban đầu là một phần của điều kiện để kết quả test đáng tin cậy. Fixture, seed, factory, dữ liệu sinh trong lúc chạy và snapshot phục vụ những nhu cầu khác nhau. Baseline cần được định nghĩa, tạo lại và xác minh; dữ liệu cần được cô lập, bảo vệ và dọn dẹp theo vòng đời rõ ràng.

Trong CI/CD, mỗi lần chạy nên có trạng thái và dữ liệu riêng ở mức phù hợp, cùng metadata để truy vết về commit, schema, dataset và môi trường. Khi setup và cleanup được tự động hóa, test ít phụ thuộc thứ tự hơn, có thể chạy song song và dễ điều tra khi thất bại. Nhờ đó, đội ngũ có được bằng chứng chất lượng ổn định trước khi đưa thay đổi đến môi trường dùng chung hoặc production.

