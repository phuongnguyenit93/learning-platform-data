# Thiết kế tạo mới, đặt lại, dọn dẹp và thời hạn tồn tại

Dữ liệu kiểm thử quyết định một bài kiểm thử bắt đầu từ trạng thái nào, có thể lặp lại ra sao và môi trường còn sạch sau khi chạy hay không. Nếu dữ liệu được tạo thủ công, phụ thuộc vào lần chạy trước hoặc dùng chung giữa nhiều test, kết quả dễ chập chờn và khó tái hiện. Nếu dữ liệu không được dọn đúng cách, queue có thể chứa message cũ, cache có thể trả bản ghi hết hạn, tài khoản thử nghiệm có thể tích tụ và các lần chạy sau có thể đọc nhầm trạng thái. Vì vậy, chiến lược dữ liệu cần quy định toàn bộ vòng đời: tạo mới, đặt lại, dọn dẹp và thời hạn tồn tại.

Trong phạm vi **VALIDATION_TESTING_STRATEGY**, thiết kế vòng đời dữ liệu kiểm thử cần bảo đảm dữ liệu đúng mục đích, có thể truy vết, được cô lập, có thể tái tạo và được xóa hoặc hết hạn theo chính sách. Mỗi loại dữ liệu cần có chủ sở hữu, phạm vi sử dụng, cách tạo, cách reset, cách cleanup và thời hạn lưu. Thiết kế phải hỗ trợ chạy riêng, chạy lặp và chạy song song mà không làm ảnh hưởng dữ liệu của người dùng hoặc nhóm khác.

## 1. Xác định vòng đời dữ liệu kiểm thử

### Bốn hoạt động cần được thiết kế cùng nhau

Vòng đời dữ liệu kiểm thử thường gồm bốn hoạt động liên kết:

1. **Tạo mới (create):** chuẩn bị dữ liệu và trạng thái ban đầu đáp ứng điều kiện của kịch bản.
2. **Đặt lại (reset):** đưa dữ liệu hoặc môi trường về trạng thái đã biết để có thể chạy lại.
3. **Dọn dẹp (cleanup):** xóa hoặc thu hồi tài nguyên do kiểm thử tạo ra sau khi hoàn tất hoặc thất bại.
4. **Hết hạn (expiration/TTL):** tự động ngừng lưu giữ dữ liệu sau thời hạn đã quy định, kể cả khi cleanup không chạy được.

Không nên xem TTL là phương án thay thế hoàn toàn cho cleanup. Cleanup giải phóng tài nguyên ngay khi có thể; TTL là lớp bảo vệ cuối để dữ liệu không tồn tại vô thời hạn khi tiến trình bị dừng hoặc teardown thất bại.

### Phân loại dữ liệu theo vòng đời

Trước khi chọn kỹ thuật, hãy xác định dữ liệu thuộc nhóm nào:

| Loại dữ liệu | Ví dụ | Cách quản lý thường dùng |
|---|---|---|
| Dữ liệu nền dùng chung | Danh mục, cấu hình tham chiếu, mã vùng | Seed có phiên bản, chỉ đọc trong test |
| Fixture theo suite | Tài khoản, tenant, sản phẩm chuẩn | Tạo ở setup suite, reset theo ranh giới suite |
| Dữ liệu theo test | Đơn hàng, phiên, giao dịch, bản ghi tạm | Tạo riêng, cleanup theo test ID |
| Dữ liệu theo lần chạy | Namespace, queue, bucket hoặc schema | Tạo theo run ID, xóa khi run kết thúc hoặc hết hạn |
| Dữ liệu phát sinh bất đồng bộ | Message, job, webhook, outbox | Theo dõi trạng thái, xử lý hết hạn và dọn theo chính sách |
| Artifact kiểm thử | File upload, báo cáo, screenshot | Lưu riêng, giới hạn quyền và TTL |
| Dữ liệu cần giữ để điều tra | Snapshot lỗi, log, trace, fixture tái hiện | Giữ theo thời hạn sự cố, sau đó xóa có kiểm soát |

Dữ liệu nền dùng chung cần bất biến trong thời gian chạy. Nếu một test có thể sửa dữ liệu nền, các test khác sẽ phụ thuộc thứ tự hoặc gặp kết quả không nhất quán. Khi cần thay đổi, hãy tạo bản sao riêng cho test.

### Mô tả trạng thái trước và sau

Với mỗi kịch bản, xác định rõ:

- Trạng thái cần có trước khi chạy.
- Dữ liệu và quan hệ được tạo mới.
- Những trường hoặc trạng thái có thể bị thay đổi.
- Tác dụng phụ phát sinh ở database, cache, queue và dịch vụ ngoài.
- Trạng thái cần đạt sau khi test hoàn tất.
- Tài nguyên nào cần giữ để điều tra và thời hạn giữ.
- Tài nguyên nào phải xóa hoặc thu hồi.

Ví dụ, kiểm thử hủy đơn hàng cần xác định đơn ở trạng thái có thể hủy, thanh toán ở sandbox, message chưa được phát hoặc đã phát, tồn kho trước và sau thao tác, email nào được phép gửi và cách dọn đơn sau test. Chỉ xóa bản ghi đơn hàng có thể chưa đủ nếu các message hoặc giao dịch liên quan vẫn còn.

## 2. Đặt yêu cầu cho dữ liệu kiểm thử

### Dữ liệu phải phù hợp mục tiêu và có thể tái tạo

Một bộ dữ liệu tốt cần:

- Đại diện cho điều kiện nghiệp vụ cần kiểm tra.
- Có giá trị và quan hệ xác định.
- Có thể tạo lại bằng cùng phiên bản fixture hoặc seed.
- Không phụ thuộc dữ liệu còn sót từ lần chạy trước.
- Không chứa bí mật hoặc dữ liệu cá nhân thật ngoài phạm vi được phép.
- Có định danh để truy vết và cleanup.
- Có thời hạn lưu và chủ sở hữu rõ ràng.

Dữ liệu ngẫu nhiên có thể hữu ích cho fuzzing hoặc property-based testing, nhưng phải lưu seed và đầu vào gây lỗi. Khi phát hiện lỗi, cần có cách chuyển dữ liệu đó thành fixture hồi quy ổn định.

### Phân biệt fixture, factory và seed

Các khái niệm thường được dùng như sau:

- **Fixture:** trạng thái hoặc tập dữ liệu chuẩn mà test cần, có thể bao gồm tài khoản, quyền, bản ghi và quan hệ.
- **Factory:** cơ chế tạo đối tượng hoặc dữ liệu theo tham số, thường giúp sinh nhiều biến thể hợp lệ.
- **Seed:** dữ liệu khởi tạo được nạp vào môi trường, thường có phiên bản và dùng lại giữa nhiều lần chạy.
- **Snapshot:** bản chụp trạng thái đã biết, dùng để khôi phục nhanh trong môi trường cô lập.
- **Test data builder:** API hoặc helper tạo một cấu trúc dữ liệu dễ đọc theo mục đích test.

Chọn cách phù hợp với cấp kiểm thử. Unit test thường dùng builder hoặc object fixture trong bộ nhớ; integration test có thể dùng factory ghi vào database thật; E2E có thể gọi API setup được bảo vệ hoặc dùng seed của môi trường.

### Xác định nguồn dữ liệu có thẩm quyền

Khi cùng một thông tin xuất hiện ở database, cache, search index và queue, cần biết nguồn nào là chuẩn. Ví dụ, trạng thái thanh toán có thể được xác nhận từ bản ghi giao dịch có thẩm quyền; cache chỉ là bản sao phục vụ đọc.

Quy định rõ oracle để kiểm tra:

- Dữ liệu chính được đọc từ đâu?
- Trạng thái bất đồng bộ được xác nhận bằng API hay event nào?
- Bản sao có thời gian hội tụ tối đa bao lâu?
- Dữ liệu nào chỉ dùng cho hiển thị và không được dùng để quyết định kết quả?
- Khi nguồn dữ liệu mâu thuẫn, nhóm nào chịu trách nhiệm xác minh?

Không kết luận dữ liệu đã được ghi đúng chỉ dựa vào giao diện nếu giao diện có thể hiển thị cache cũ.

## 3. Tạo mới dữ liệu một cách có kiểm soát

### Tạo dữ liệu theo cấp kiểm thử

Mỗi cấp có cách chuẩn bị phù hợp:

| Cấp kiểm thử | Cách tạo dữ liệu phù hợp | Lưu ý |
|---|---|---|
| Unit | Object builder, fixture trong bộ nhớ, fake clock | Không cần phụ thuộc hạ tầng ngoài |
| Component | Factory và database/schema cô lập | Xác minh mapping và ràng buộc thật |
| Integration | API setup, seed có phiên bản, container riêng | Bao gồm quan hệ và cấu hình phụ thuộc |
| System/E2E | Tài khoản và tenant thử nghiệm, API quản trị được bảo vệ | Theo dõi tác dụng phụ xuyên dịch vụ |
| Performance | Dataset có kích thước và phân bố đại diện | Ghi rõ seed, số lượng và cách tạo |
| Resilience/Recovery | Snapshot hoặc dữ liệu có invariant kiểm tra được | Có kế hoạch phục hồi và đối soát |

Không dùng cùng một phương pháp tạo dữ liệu cho mọi cấp. Ví dụ, tạo trực tiếp bản ghi database trong E2E có thể bỏ qua quy tắc nghiệp vụ mà người dùng thực sự đi qua. Ngược lại, tạo toàn bộ dữ liệu qua giao diện có thể làm suite chậm và dễ lỗi.

### Dùng factory và builder có ý nghĩa nghiệp vụ

Factory nên cung cấp mặc định hợp lệ và cho phép ghi đè những thuộc tính liên quan đến mục tiêu test. Tên hàm nên diễn đạt trạng thái nghiệp vụ, chẳng hạn tạo thành viên đang hoạt động, tạo đơn chờ xử lý hoặc tạo lời mời đã hết hạn, thay vì chỉ tạo một đối tượng với nhiều tham số khó hiểu.

Ví dụ minh họa:

~~~typescript
const tenant = await testData.createTenant();
const member = await testData.createMember({
  tenantId: tenant.id,
  role: "EDITOR",
  status: "ACTIVE"
});

const invitation = await testData.createInvitation({
  tenantId: member.tenantId,
  email: uniqueTestEmail(),
  expiresAt: fixedClock.now().plus({ days: 2 })
});
~~~

Ví dụ chỉ minh họa cách diễn đạt. Trong hệ thống thật, factory phải dùng API hoặc cơ chế được hỗ trợ, kiểm tra quyền và ghi nhận tài nguyên được tạo để cleanup.

### Tạo dữ liệu theo thứ tự phụ thuộc

Một số dữ liệu cần quan hệ cha-con. Hãy mô tả thứ tự tạo và thứ tự dọn:

- Tạo tenant trước thành viên.
- Tạo khách hàng trước đơn hàng.
- Tạo đơn hàng trước giao dịch liên quan.
- Tạo job trước khi phát event nếu hợp đồng yêu cầu.
- Tạo đối tượng tham chiếu trước bản ghi phụ thuộc.

Khi setup thất bại giữa chừng, phải biết những tài nguyên nào đã được tạo để dọn phần đã hoàn thành. Setup nên ghi lại ID ngay sau mỗi thao tác thành công thay vì chỉ lưu tất cả khi kết thúc.

### Dùng ID duy nhất và namespace

Để tránh xung đột giữa test, tạo định danh theo run ID và test ID. Có thể dùng:

- Prefix cho tên tenant, tài khoản hoặc tài nguyên.
- UUID hoặc ID sinh riêng cho mỗi test.
- Schema hoặc database riêng cho mỗi worker.
- Cache key prefix.
- Queue/topic hoặc subscription riêng khi hạ tầng cho phép.
- Thư mục hoặc bucket riêng cho file.

Định danh nên đủ duy nhất nhưng không chứa mật khẩu, token, email thật hoặc dữ liệu nhạy cảm. Ghi ID vào báo cáo để người điều tra tìm được tài nguyên tương ứng.

### Seed dữ liệu nền có phiên bản

Seed dùng chung nên được quản lý như một artifact có phiên bản. Khi thay đổi seed:

- Ghi version hoặc checksum.
- Xác định migration hoặc cách nâng cấp.
- Xác minh dữ liệu cũ còn tương thích.
- Chỉ cho phép test đọc nếu mục tiêu không yêu cầu sửa.
- Có quy trình reset về seed chuẩn.
- Không để nhiều suite đồng thời sửa cùng seed.

Nếu dữ liệu nền lớn, có thể dùng snapshot được tạo từ seed đã kiểm tra. Cần bảo đảm snapshot không chứa dữ liệu production nhạy cảm.

## 4. Thiết kế reset để có thể chạy lại an toàn

### Phân biệt reset với cleanup

Reset đưa dữ liệu hoặc môi trường về trạng thái ban đầu để chạy lại. Cleanup xóa hoặc thu hồi tài nguyên sau khi không còn cần. Một số cách reset giữ nguyên dữ liệu nền; một số cách xóa toàn bộ namespace rồi tạo lại.

Ví dụ:

- Reset một test: xóa đơn hàng của test rồi tạo đơn mới.
- Reset suite: rollback transaction hoặc nạp lại fixture.
- Reset database: tạo schema mới từ migration và seed.
- Reset môi trường E2E: xóa tenant test và các tài nguyên liên quan, sau đó khởi tạo lại.
- Reset worker: xóa job/message thuộc run, xác minh consumer không còn xử lý tác vụ cũ.

Không reset một tài nguyên dùng chung khi test khác vẫn đang sử dụng nó.

### Chọn chiến lược reset phù hợp

| Chiến lược | Cách hoạt động | Ưu điểm | Giới hạn |
|---|---|---|---|
| Transaction rollback | Thực hiện test trong transaction rồi rollback | Nhanh, ít để lại dữ liệu | Không phù hợp với tác dụng phụ ngoài transaction hoặc nhiều kết nối độc lập |
| Xóa theo namespace | Xóa bản ghi có run/test ID | Hỗ trợ chạy song song nếu namespace riêng | Phải theo dõi đầy đủ quan hệ và tài nguyên ngoài database |
| Tạo schema/database mới | Tạo môi trường dữ liệu riêng cho run | Cô lập mạnh, dễ bỏ toàn bộ | Tốn thời gian và tài nguyên |
| Restore snapshot | Khôi phục bản chụp trạng thái chuẩn | Nhanh với dataset lớn | Snapshot phải đúng phiên bản và không chứa dữ liệu nhạy cảm |
| Re-seed | Xóa dữ liệu biến đổi rồi nạp lại seed | Dễ hiểu, có thể lặp | Có thể chậm và cần quản lý phụ thuộc |
| API reset được bảo vệ | Gọi chức năng quản trị trong môi trường test | Giữ quy tắc nghiệp vụ và dễ tự động hóa | Cần giới hạn quyền và không được mở rộng thành đường xóa production |

Có thể kết hợp nhiều chiến lược. Ví dụ, dùng database riêng cho mỗi worker, transaction rollback cho test đơn vị tích hợp và cleanup theo run ID cho queue hoặc file.

### Bảo đảm reset có tính idempotent

Một thao tác reset idempotent có thể chạy nhiều lần mà vẫn đưa hệ thống về cùng trạng thái mục tiêu. Ví dụ, xóa tài nguyên đã không còn tồn tại không nên làm cleanup thất bại nếu kết quả cuối vẫn đúng.

Hãy xác minh:

- Reset lần đầu thành công.
- Reset lặp lại vẫn thành công.
- Reset sau khi setup chỉ hoàn thành một phần vẫn dọn được.
- Reset không xóa tài nguyên của run khác.
- Sau reset, dữ liệu nền và invariant đúng.
- Cache, queue và search index cũng được xử lý theo chính sách.

### Chọn thời điểm reset

Reset có thể thực hiện trước mỗi test, trước mỗi suite, giữa các bước hoặc sau khi chạy. Cần xác định ranh giới dựa trên tính độc lập và chi phí:

- Test cần trạng thái riêng: reset hoặc tạo mới trước mỗi test.
- Nhiều test chỉ đọc dữ liệu nền: có thể dùng chung fixture bất biến.
- Hành trình nhiều bước: giữ trạng thái trong một test có phạm vi rõ.
- Test tải: reset giữa các vòng để không làm lệch số liệu.
- Test phục hồi: cần giữ trạng thái có chủ đích để xác minh sau lỗi.

Không reset quá sớm nếu cần giữ bằng chứng điều tra, và không giữ quá lâu nếu tài nguyên có thể ảnh hưởng đến test khác.

## 5. Dọn dẹp dữ liệu và tài nguyên sau kiểm thử

### Xây dựng danh mục tài nguyên cần cleanup

Cleanup không chỉ giới hạn ở bản ghi chính. Một hành trình có thể tạo:

- Tài khoản, tenant, phiên và token.
- Bản ghi nghiệp vụ và bản ghi liên quan.
- File upload, báo cáo và object storage.
- Cache key và search index.
- Queue message, job, outbox và dead-letter record.
- Webhook subscription hoặc endpoint tạm.
- Giao dịch sandbox, hóa đơn hoặc tác vụ nhà cung cấp.
- Log, trace và artifact cần lưu theo thời hạn riêng.

Mỗi tài nguyên cần chỉ rõ cách tìm, người sở hữu, quyền xóa và điều kiện giữ lại.

### Cleanup theo dependency graph

Nếu tài nguyên có quan hệ phụ thuộc, thứ tự xóa thường ngược với thứ tự tạo. Ví dụ, xóa giao dịch và message liên quan trước khi xóa đơn hàng hoặc tenant. Tuy nhiên, một số hệ thống có audit hoặc retention bắt buộc nên không được xóa bản ghi theo cách thông thường.

Hãy lập dependency graph và xác định ngoại lệ. Không dùng lệnh xóa cascade rộng nếu chưa biết phạm vi dữ liệu liên quan.

~~~mermaid
flowchart TD
    A["Tạo tenant test"] --> B["Tạo thành viên"]
    B --> C["Tạo đơn hàng"]
    C --> D["Tạo giao dịch sandbox"]
    C --> E["Phát message"]
    E --> F["Tạo job / artifact"]
    F --> G["Xác minh kết quả"]
    G --> H["Cleanup tài nguyên theo run ID"]
    H --> I["Xác minh không còn tài nguyên ngoài chính sách giữ lại"]
~~~

Sơ đồ mô tả luồng đơn giản. Thứ tự cleanup thực tế cần dựa trên quan hệ và chính sách lưu giữ của từng thành phần.

### Dùng teardown an toàn kể cả khi test fail

Teardown nên chạy trong khối đảm bảo thực thi, hook sau test hoặc quy trình dọn dẹp độc lập. Cần thiết kế cho các tình huống:

- Setup tạo được một phần rồi lỗi.
- Assertion thất bại giữa hành trình.
- Runner bị dừng đột ngột.
- Mạng mất khi cleanup.
- Tài nguyên đã bị xóa bởi một tiến trình khác.
- Cleanup của một loại tài nguyên thất bại nhưng loại khác vẫn cần được xử lý.

Không để lỗi cleanup che mất lỗi kiểm thử chính. Báo cáo cần lưu riêng lỗi chính và lỗi cleanup, cùng danh sách tài nguyên còn lại.

### Cleanup phải có phạm vi an toàn

Mọi thao tác xóa nên giới hạn theo run ID, test ID hoặc namespace đã xác định. Trước khi xóa, có thể kiểm tra marker sở hữu, môi trường và trạng thái tài nguyên. Quyền cleanup chỉ nên cho phép xóa tài nguyên test trong phạm vi được giao.

Không dùng lệnh xóa toàn bộ database, bucket, queue hoặc tenant dùng chung để dọn một test. Với dữ liệu không thể đảo ngược hoặc có retention, dùng sandbox hoặc quy trình bù trừ thay vì cố xóa trực tiếp.

### Xác minh sau cleanup

Cleanup hoàn tất khi các tài nguyên thuộc phạm vi đã được xử lý theo chính sách, không phải chỉ khi lệnh xóa trả thành công. Xác minh:

- Không còn bản ghi hoặc tài nguyên tạm ngoài danh sách được giữ.
- Không còn message/job có thể tác động đến test tiếp theo.
- Cache và index không còn dữ liệu lỗi thời do test tạo.
- Token, phiên hoặc quyền tạm đã bị thu hồi.
- File và object được xóa hoặc chuyển sang vùng lưu giữ đúng.
- Audit record cần giữ vẫn còn theo chính sách.
- Không có tài nguyên của run khác bị ảnh hưởng.

## 6. Thiết kế thời hạn tồn tại và TTL

### TTL là gì và áp dụng ở đâu?

TTL (time to live) là thời hạn một dữ liệu hoặc tài nguyên được phép tồn tại trước khi hết hiệu lực hoặc bị xóa theo chính sách. TTL có thể áp dụng cho:

- Tài khoản hoặc tenant thử nghiệm tạm thời.
- Phiên, token và lời mời.
- Cache key.
- Queue message và job.
- File upload và báo cáo.
- Webhook endpoint hoặc subscription.
- Snapshot, log và artifact kiểm thử.
- Namespace hoặc database theo run.

TTL có thể mang ý nghĩa hết hiệu lực nghiệp vụ hoặc xóa vật lý. Ví dụ, token hết hạn có thể bị từ chối ngay cả khi bản ghi vẫn còn trong storage; một file có thể được đánh dấu hết hạn trước khi tiến trình purge xóa nó. Phải phân biệt hai thời điểm này.

### Đặt TTL theo mục đích và rủi ro

Không nên đặt một TTL chung cho mọi loại dữ liệu. Hãy cân nhắc:

- Thời gian cần thiết để chạy test và điều tra lỗi.
- Độ trễ bất đồng bộ và thời gian retry.
- Nhu cầu giữ artifact để tái hiện.
- Dung lượng và chi phí lưu trữ.
- Mức nhạy cảm của dữ liệu.
- Nghĩa vụ audit hoặc retention.
- Khả năng cleanup bị gián đoạn.
- Mức ảnh hưởng nếu dữ liệu hết hạn quá sớm hoặc quá muộn.

TTL quá ngắn có thể xóa fixture trước khi test hoàn tất hoặc làm mất bằng chứng khi điều tra. TTL quá dài làm tích tụ dữ liệu, tăng chi phí và rủi ro lộ thông tin.

### Phân biệt TTL với retention

TTL thường mô tả thời gian sống của một mục dữ liệu hoặc tài nguyên. Retention policy quy định dữ liệu phải hoặc được phép lưu trong khoảng thời gian nào, có thể bao gồm yêu cầu pháp lý, audit, điều tra và xóa an toàn.

Một số dữ liệu kiểm thử có thể cần giữ lâu hơn thời gian chạy để điều tra lỗi, nhưng không được giữ lâu hơn chính sách tổ chức. Nếu chính sách retention yêu cầu giữ audit record, cleanup không được xóa nó chỉ vì test đã kết thúc.

### Tính TTL từ thời điểm nào?

Cần định nghĩa điểm bắt đầu:

- Từ lúc tạo tài nguyên.
- Từ lần truy cập cuối.
- Từ khi test kết thúc.
- Từ khi run bị đánh dấu thất bại.
- Từ khi artifact được tạo.
- Từ mốc thời gian do hệ thống nghiệp vụ quy định.

Với dữ liệu test theo run, TTL tính từ lúc tạo thường dễ quản lý và bảo đảm tài nguyên có giới hạn ngay cả khi runner bị mất. Nếu TTL tính từ lần truy cập cuối, một test lỗi có thể liên tục gia hạn tài nguyên và khiến dữ liệu tồn tại vô hạn. Cần có giới hạn tuổi tối đa.

### Kiểm tra hành vi hết hạn

Với mỗi loại dữ liệu có TTL, kiểm tra:

- Dữ liệu còn hợp lệ trước thời điểm hết hạn.
- Dữ liệu bị từ chối hoặc đánh dấu hết hạn đúng thời điểm.
- Tiến trình purge xóa vật lý trong khoảng trễ được chấp nhận.
- TTL được giữ đúng khi cập nhật hoặc sao chép dữ liệu.
- Đồng hồ lệch không làm dữ liệu hết hạn quá sớm hoặc quá muộn ngoài giới hạn.
- Tác vụ đang chạy có chính sách xử lý rõ khi tài nguyên hết hạn.
- Dữ liệu cần giữ để audit không bị purge trái chính sách.

Không kiểm tra TTL bằng sleep dài không kiểm soát. Dùng clock giả lập cho logic hết hạn nếu có thể; với tiến trình purge thực, kiểm tra lịch chạy, độ trễ và trạng thái sau khi job hoàn tất.

## 7. Quản lý dữ liệu bất đồng bộ và tài nguyên phân tán

### Theo dõi message, job và outbox

Một test có thể kết thúc trước khi worker xử lý xong. Nếu cleanup xóa dữ liệu đầu vào trong khi worker vẫn chạy, hệ thống có thể phát sinh lỗi hoặc tác dụng phụ ngoài dự kiến.

Cần xác định:

- Test có chờ job đạt trạng thái cuối trước cleanup không?
- Message được ack, retry hoặc chuyển DLQ theo quy tắc nào?
- Có thể hủy job an toàn không?
- Event ID hoặc run ID nào liên kết message với test?
- Outbox record cần giữ để đối soát không?
- Worker có thể tiếp tục sau khi runner đã kết thúc không?

Với test cần kiểm tra retry hoặc phục hồi, không dọn message trước khi đã thu thập bằng chứng. Dùng namespace hoặc queue riêng khi phù hợp.

### Xử lý tác dụng phụ từ nhà cung cấp

Dịch vụ ngoài có thể giữ dữ liệu sau khi test kết thúc, ví dụ giao dịch sandbox, webhook subscription hoặc email sink. Hãy:

- Dùng tài khoản và môi trường sandbox.
- Gắn external reference ID theo run/test ID.
- Lưu trạng thái và mã tham chiếu để đối soát.
- Dùng API hủy hoặc xóa của nhà cung cấp nếu có.
- Đặt TTL hoặc retention theo chính sách sandbox.
- Ghi rõ tài nguyên không thể xóa và thời hạn nhà cung cấp tự dọn.

Không gửi thông báo hoặc giao dịch thật chỉ để kiểm tra cleanup. Nếu nhà cung cấp không hỗ trợ xóa, cần giới hạn dữ liệu và thời hạn ngay từ bước tạo.

### Xử lý cache và search index

Xóa bản ghi database không đồng nghĩa cache và search index đã sạch. Cần kiểm tra:

- Cache key theo namespace đã bị xóa hoặc hết hạn.
- Invalidation event đã được xử lý.
- Search document được xóa hoặc cập nhật.
- Replica hoặc read model đã hội tụ.
- Không có consumer tạo lại dữ liệu từ message còn sót.

Nếu dùng eventual consistency, cleanup cần chờ trạng thái hội tụ có giới hạn và xác minh sau thời hạn. Tránh dùng sleep cố định mà không kiểm tra trạng thái.

### Phối hợp cleanup giữa nhiều thành phần

Có thể dùng một registry tài nguyên theo run ID để ghi nhận tài nguyên đã tạo và trạng thái cleanup. Registry giúp tiến trình dọn dẹp độc lập tìm tài nguyên khi runner bị dừng.

Ví dụ cấu trúc:

~~~json
{
  "runId": "run-2026-11-16-a81f",
  "owner": "test-suite-orders",
  "environment": "integration",
  "createdAt": "2026-11-16T08:00:00Z",
  "expiresAt": "2026-11-16T10:00:00Z",
  "resources": [
    {"type": "tenant", "id": "tenant-test-a81f", "state": "created"},
    {"type": "order", "id": "order-test-a81f", "state": "created"},
    {"type": "queue-message", "id": "event-test-a81f", "state": "pending"}
  ]
}
~~~

Đây là ví dụ minh họa. Registry không nên chứa secret hoặc payload nhạy cảm; cần phân quyền, retention và cách cập nhật trạng thái an toàn.

## 8. Bảo vệ dữ liệu và môi trường khi tạo, reset, cleanup

### Dùng dữ liệu tổng hợp hoặc đã khử định danh

Dữ liệu kiểm thử nên được tạo tổng hợp hoặc khử định danh theo chính sách. Tránh sao chép dữ liệu production sang môi trường test nếu chưa có cơ sở và quy trình được phê duyệt.

Cần kiểm tra:

- Tên, email, số điện thoại và địa chỉ không thuộc người thật ngoài ý muốn.
- Token, password, secret và khóa không được lưu trong fixture hoặc log.
- Dữ liệu thanh toán dùng sandbox hoặc giá trị thử nghiệm được nhà cung cấp chấp nhận.
- Artifact và snapshot không chứa dữ liệu nhạy cảm.
- Dữ liệu được phân quyền theo tenant và vai trò.
- Bản sao lưu test có thời hạn và quyền truy cập rõ.

### Phân quyền thao tác dữ liệu

Tách quyền tạo, đọc, reset và xóa nếu cần. Ví dụ, test runner có thể tạo và xóa tài nguyên trong namespace của nó nhưng không được xóa tenant dùng chung hoặc đọc dữ liệu của tenant khác.

Các thao tác reset diện rộng cần có bảo vệ bổ sung:

- Xác nhận môi trường đích.
- Kiểm tra namespace hoặc marker sở hữu.
- Giới hạn tài khoản và quyền.
- Audit thao tác.
- Có phương án khôi phục nếu dữ liệu bị xóa nhầm.

### Tránh chạy cleanup trên production

Các cơ chế cleanup và reset phải mặc định bị giới hạn ở môi trường test. Nếu một công cụ có thể chạy trên nhiều môi trường, phải xác minh môi trường và quyền trước khi thực hiện. Không dựa vào một biến môi trường dễ bị thiếu để bảo vệ thao tác xóa diện rộng.

Với production, dữ liệu kiểm thử hoặc synthetic monitoring cần tuân theo quy trình riêng, dùng tài khoản và tài nguyên được phê duyệt, có tác dụng phụ giới hạn và không dùng cleanup tổng quát.

## 9. Thiết kế quy trình vận hành vòng đời dữ liệu

### Quy trình setup, test, teardown

Một quy trình chuẩn có thể gồm:

1. Tạo run ID và namespace.
2. Kiểm tra môi trường, quyền và giới hạn tài nguyên.
3. Tạo fixture nền cần thiết.
4. Tạo dữ liệu theo test và ghi registry.
5. Xác minh trạng thái trước khi thực thi.
6. Chạy test và thu thập bằng chứng.
7. Chờ hoặc hủy tác vụ bất đồng bộ theo chính sách.
8. Cleanup tài nguyên theo dependency graph.
9. Xác minh trạng thái sau cleanup.
10. Lưu artifact cần thiết theo retention.
11. Đánh dấu run đã hoàn tất và đặt TTL cho phần còn lại.

Nếu bất kỳ bước nào thất bại, ghi nhận trạng thái và cho phép quy trình cleanup tiếp tục hoặc được chạy lại an toàn.

### Dọn dẹp định kỳ cho tài nguyên bị bỏ sót

Một tiến trình janitor hoặc sweeper có thể tìm tài nguyên test quá hạn và dọn chúng. Nó nên:

- Chỉ xử lý namespace có marker test và chủ sở hữu rõ.
- Kiểm tra expiresAt hoặc TTL.
- Bỏ qua tài nguyên đang được run hợp lệ sử dụng.
- Ghi log/audit kết quả.
- Retry lỗi tạm thời có giới hạn.
- Đưa tài nguyên không thể xóa vào danh sách cần điều tra.
- Có metric về số lượng tài nguyên quá hạn và cleanup thất bại.

Janitor không nên xóa theo tên gần giống hoặc pattern rộng mà không xác minh ownership. Một thao tác purge sai có thể gây mất dữ liệu ngoài phạm vi.

### Theo dõi tình trạng dữ liệu

Có thể theo dõi:

- Số tài nguyên test đang tồn tại theo môi trường.
- Số tài nguyên quá TTL.
- Tuổi của dữ liệu test lâu nhất.
- Tỷ lệ cleanup thành công.
- Số run kết thúc nhưng còn tài nguyên.
- Dung lượng fixture, snapshot và artifact.
- Số message/job test còn tồn.
- Số lần cleanup phải retry hoặc can thiệp thủ công.

Các chỉ số này giúp phát hiện dữ liệu tích tụ trước khi làm môi trường chậm hoặc gây xung đột.

## 10. Ví dụ: vòng đời dữ liệu cho E2E tạo đơn hàng

Giả sử một E2E kiểm tra người dùng tạo đơn, thanh toán sandbox, nhận sự kiện và xem trạng thái đơn. Hành trình sử dụng tenant, thành viên, sản phẩm, đơn hàng, giao dịch, queue message và email sink.

### Tạo mới

- Sinh run ID và tenant riêng.
- Tạo thành viên với vai trò cần kiểm tra.
- Tạo sản phẩm và tồn kho có giá trị cố định.
- Cấu hình payment sandbox với external reference gắn run ID.
- Tạo email sink hoặc địa chỉ nhận test.
- Ghi tất cả ID vào registry.
- Xác minh trạng thái ban đầu trước khi thực hiện hành trình.

### Thực thi và xác minh

- Gửi yêu cầu tạo đơn với idempotency key.
- Chờ đơn chuyển trạng thái cuối bằng API trạng thái có thẩm quyền.
- Xác minh giao dịch sandbox và event ID.
- Xác minh tồn kho, hóa đơn và audit event.
- Kiểm tra email sink nhận đúng người nhận và số lần.
- Lưu trace, log và ID cần thiết để điều tra.

### Đặt lại và dọn dẹp

Nếu test cần chạy lại:

- Xác nhận worker đã hoàn tất hoặc hủy job an toàn.
- Xóa message còn chờ thuộc run hoặc reset queue namespace.
- Hủy giao dịch sandbox nếu nhà cung cấp hỗ trợ.
- Xóa email sink data theo API sandbox.
- Xóa đơn hàng và dữ liệu liên quan theo thứ tự phụ thuộc.
- Xóa cache key và search document.
- Thu hồi phiên và xóa tenant test.
- Xác minh không còn tài nguyên ngoài artifact được giữ lại.

Nếu test thất bại giữa lúc thanh toán đang xử lý, không xóa ngay dữ liệu cần đối soát. Đánh dấu run cần điều tra, giữ các ID và artifact cần thiết trong thời hạn ngắn đã quy định, rồi cleanup sau khi có kết luận.

### Chính sách TTL mẫu

| Tài nguyên | Thời hạn minh họa | Lý do |
|---|---|---|
| Tenant và dữ liệu E2E | 2 giờ sau khi run kết thúc | Cho phép điều tra ngắn, sau đó dọn |
| Message test chưa xử lý | Theo retention queue ngắn và run status | Tránh message cũ ảnh hưởng run mới |
| Cache key test | Không vượt quá thời hạn dữ liệu test | Ngăn dữ liệu cũ được đọc lại |
| Screenshot và trace khi pass | Thời hạn ngắn theo chính sách CI | Giảm dung lượng |
| Artifact khi fail | Thời hạn dài hơn nhưng có giới hạn | Hỗ trợ điều tra và tái hiện |
| Audit record bắt buộc | Theo chính sách audit | Cleanup test không được xóa trái quy định |

Các thời hạn chỉ là ví dụ, cần thay bằng chính sách thực tế về điều tra, bảo mật, dung lượng và retention.

## 11. Tiêu chí lựa chọn và kiểm chứng chiến lược dữ liệu

### Tiêu chí cho dữ liệu có thể tái tạo

- Có nguồn tạo hoặc seed được quản lý phiên bản.
- Có ID và quan hệ rõ ràng.
- Có thể tạo từ đầu trong môi trường sạch.
- Có thể xác minh trạng thái trước khi test.
- Không phụ thuộc kết quả của test khác.
- Dữ liệu ngẫu nhiên có seed và đầu vào lưu lại.

### Tiêu chí cho reset và cleanup

- Reset có thể lặp lại và đưa dữ liệu về trạng thái xác định.
- Cleanup giới hạn theo quyền sở hữu và namespace.
- Setup thất bại giữa chừng vẫn có thể cleanup.
- Cleanup có thể chạy lại khi gặp lỗi tạm thời.
- Tài nguyên bất đồng bộ được xử lý trước hoặc theo chính sách riêng.
- Không xóa dữ liệu cần giữ cho audit hoặc điều tra.
- Trạng thái sau cleanup được xác minh.

### Tiêu chí cho TTL

- Mỗi loại tài nguyên có thời hạn và điểm bắt đầu rõ.
- TTL phù hợp với thời gian chạy, retry và điều tra.
- Hết hiệu lực và xóa vật lý được phân biệt.
- Có tiến trình xử lý dữ liệu hết hạn.
- Có giới hạn tuổi tối đa khi TTL được gia hạn.
- Cleanup và TTL không xung đột với retention bắt buộc.
- Tài nguyên quá hạn và purge thất bại được giám sát.

### Kiểm thử chính cơ chế quản lý dữ liệu

Cần có kiểm tra cho công cụ fixture, reset, cleanup và janitor:

- Tạo dữ liệu hai lần có tạo trùng ngoài dự kiến không?
- Reset có đưa dữ liệu về đúng trạng thái không?
- Cleanup có xóa nhầm tài nguyên khác không?
- Cleanup có hoạt động sau setup một phần không?
- TTL có hết hạn đúng và purge trong giới hạn không?
- Tài nguyên đang được sử dụng có bị xóa sớm không?
- Janitor có nhận diện đúng tài nguyên thuộc test không?
- Khi cleanup thất bại, có thể retry và điều tra không?

Công cụ quản lý dữ liệu kiểm thử cũng là phần mềm cần được xác minh. Một lỗi trong helper cleanup có thể ảnh hưởng đến nhiều suite hoặc xóa dữ liệu ngoài ý muốn.

## 12. Những sai lầm thường gặp

- **Chỉ tạo dữ liệu mà không quản lý vòng đời:** dữ liệu tích tụ và làm sai lệch lần chạy sau.
- **Dùng dữ liệu dùng chung có thể thay đổi:** test phụ thuộc thứ tự và chạy song song không an toàn.
- **Cleanup chỉ xóa bản ghi chính:** bỏ sót cache, queue, file hoặc dữ liệu nhà cung cấp.
- **Giả định teardown luôn chạy:** runner có thể bị dừng hoặc mất kết nối.
- **Dùng TTL thay cho cleanup:** tài nguyên tồn tại lâu hơn cần thiết và có thể gây tác dụng phụ trong thời gian chờ hết hạn.
- **Đặt TTL quá ngắn:** dữ liệu hoặc artifact biến mất trước khi test hay điều tra hoàn tất.
- **Không ghi ID tài nguyên:** không thể tìm đúng dữ liệu cần reset hoặc cleanup.
- **Xóa theo pattern rộng:** có thể ảnh hưởng dữ liệu của run hoặc nhóm khác.
- **Reset database dùng chung:** làm hỏng test đang chạy hoặc môi trường của nhóm khác.
- **Không xử lý tác vụ bất đồng bộ:** worker tiếp tục dùng dữ liệu đã bị xóa.
- **Bỏ qua nguồn dữ liệu có thẩm quyền:** cache hoặc read model cũ bị hiểu nhầm là trạng thái đúng.
- **Giữ artifact vô thời hạn:** tăng chi phí và rủi ro lộ dữ liệu.
- **Không kiểm thử janitor:** tiến trình tự động dọn có thể xóa nhầm hoặc bỏ sót tài nguyên.
- **Dùng dữ liệu production không kiểm soát:** tạo rủi ro quyền riêng tư và bảo mật.

## 13. Đầu ra cần có trước khi chốt thiết kế vòng đời dữ liệu

Một kế hoạch đủ dùng nên có:

1. **Danh mục dữ liệu:** loại, mục đích, nguồn, chủ sở hữu và độ nhạy cảm.
2. **Mô hình phụ thuộc:** quan hệ giữa tài khoản, tenant, bản ghi, message, file và dịch vụ ngoài.
3. **Quy tắc tạo mới:** fixture, factory, seed, snapshot, ID và namespace.
4. **Trạng thái chuẩn:** điều kiện trước, trạng thái cuối và nguồn dữ liệu có thẩm quyền.
5. **Chiến lược reset:** phạm vi, thời điểm, cách thực hiện và tính idempotent.
6. **Chiến lược cleanup:** dependency graph, quyền, xử lý lỗi và xác minh sau xóa.
7. **Chính sách TTL/retention:** thời hạn, điểm bắt đầu, gia hạn, hết hiệu lực và xóa vật lý.
8. **Quản lý bất đồng bộ:** message, job, webhook, outbox và tác dụng phụ cần đối soát.
9. **Kiểm soát bảo mật:** dữ liệu tổng hợp, phân quyền, secret, audit và môi trường.
10. **Giám sát:** tài nguyên quá hạn, cleanup thất bại, dung lượng và run còn sót.
11. **Quy trình phục hồi:** xử lý setup một phần, runner bị dừng và cleanup không hoàn tất.
12. **Ví dụ và tiêu chí xác minh:** kịch bản đại diện chứng minh toàn bộ vòng đời hoạt động.

Trước khi đưa chiến lược vào sử dụng, hãy rà soát:

- Mỗi test có thể tạo dữ liệu cần thiết từ trạng thái sạch không?
- Fixture và seed có phiên bản và có thể tái tạo không?
- ID và namespace có ngăn va chạm giữa các run không?
- Reset có an toàn, idempotent và không ảnh hưởng tài nguyên dùng chung không?
- Cleanup có bao phủ database, cache, queue, file và dịch vụ ngoài không?
- Setup hoặc teardown thất bại giữa chừng có thể phục hồi không?
- TTL có đủ dài cho chạy test và điều tra nhưng vẫn giới hạn tuổi dữ liệu không?
- Hết hiệu lực và xóa vật lý có được kiểm tra riêng không?
- Retention bắt buộc và audit record có được bảo toàn không?
- Có giám sát tài nguyên quá hạn và cleanup thất bại không?
- Dữ liệu nhạy cảm và quyền xóa có được kiểm soát không?

Thiết kế tạo mới, đặt lại, dọn dẹp và thời hạn tồn tại giúp dữ liệu kiểm thử trở thành một phần có quản trị của chiến lược xác thực. Khi dữ liệu được tạo có chủ đích, cô lập theo phạm vi, reset an toàn và hết hạn đúng chính sách, nhóm có thể chạy lặp và song song với kết quả đáng tin cậy. Hãy xem lại vòng đời dữ liệu khi hành trình, kiến trúc, phụ thuộc hoặc yêu cầu lưu giữ thay đổi.

