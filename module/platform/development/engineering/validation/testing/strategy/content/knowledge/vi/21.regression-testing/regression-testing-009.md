# Quản lý thời gian chạy và dữ liệu cho bộ kiểm thử tăng dần

Khi sản phẩm phát triển, bộ kiểm thử hồi quy thường tăng theo số chức năng, quy tắc nghiệp vụ, nền tảng và tích hợp. Chạy toàn bộ bộ kiểm thử sau mọi thay đổi có thể làm phản hồi kéo dài, tăng chi phí máy chạy và khiến nhóm chờ lâu trước khi biết một thay đổi có an toàn hay không. Nếu chỉ chọn một vài test nhanh mà không dựa trên tác động thay đổi, lỗi ở khu vực liên quan có thể bị bỏ sót. Dữ liệu cũng tạo ra thách thức tương tự: dùng chung dữ liệu giúp giảm thời gian chuẩn bị nhưng dễ xung đột khi chạy song song; tạo mới mọi thứ cho mỗi test tăng độ độc lập nhưng có thể làm suite chậm đáng kể.

Trong phạm vi **VALIDATION_TESTING_STRATEGY**, quản lý thời gian chạy và dữ liệu cho bộ kiểm thử tăng dần là việc thiết kế cách chọn, sắp xếp, thực thi và duy trì các kiểm thử hồi quy theo mức độ thay đổi và rủi ro. Mục tiêu là đưa ra phản hồi sớm với bằng chứng phù hợp, giữ khả năng phát hiện lỗi và bảo đảm dữ liệu có thể tái tạo, cô lập, làm mới và dọn dẹp. “Tăng dần” không có nghĩa là chỉ chạy ít test; đó là chiến lược phân bổ kiểm tra theo từng vòng, đồng thời duy trì một đường chạy rộng hơn để phát hiện lỗi ngoài vùng tác động dự kiến.

## 1. Hiểu bộ kiểm thử hồi quy tăng dần

### Hồi quy tăng dần là gì?

Kiểm thử hồi quy tăng dần (incremental regression testing) chọn và chạy các phần kiểm thử phù hợp với thay đổi hiện tại, sau đó mở rộng phạm vi theo rủi ro, mức độ tích hợp và giai đoạn phát hành. Việc lựa chọn có thể dựa trên:

- Tệp, module, API hoặc thành phần đã thay đổi.
- Quan hệ phụ thuộc và luồng dữ liệu giữa các thành phần.
- Yêu cầu, quy tắc nghiệp vụ và rủi ro bị ảnh hưởng.
- Lịch sử lỗi và khu vực thường xuyên phát sinh hồi quy.
- Loại thay đổi như mã nguồn, schema, cấu hình, dependency hoặc feature flag.
- Mức độ tin cậy của ánh xạ giữa thay đổi và test.

Một thay đổi nhỏ trong hàm tính phí có thể cần unit test, test hợp đồng và một số hành trình thanh toán liên quan. Một thay đổi ở thư viện xác thực dùng chung có thể ảnh hưởng đến nhiều module, do đó phạm vi hồi quy phải rộng hơn. Nếu không thể xác định tác động đáng tin cậy, nhóm cần mở rộng lựa chọn hoặc chạy bộ rộng hơn.

### Phân biệt incremental testing với kiểm thử chọn ngẫu nhiên

Lựa chọn tăng dần phải có căn cứ. Chọn test vì chúng chạy nhanh hoặc tình cờ pass gần đây không bảo đảm chúng liên quan đến thay đổi. Một chiến lược hợp lý cần giải thích:

- Vì sao test được chọn.
- Những thành phần và yêu cầu nào được đại diện.
- Những khu vực nào chưa được kiểm tra trong vòng hiện tại.
- Khi nào cần mở rộng đến suite rộng hơn.
- Điều kiện nào khiến kết quả lựa chọn tự động không đáng tin cậy.

Test chọn theo tác động là một lớp bảo vệ có mục tiêu, không phải bằng chứng rằng mọi vùng ngoài phạm vi đều an toàn.

### Phân biệt thời gian phản hồi với tổng thời gian máy chạy

Thời gian mà nhà phát triển chờ và tổng tài nguyên CI sử dụng là hai đại lượng khác nhau. Chạy nhiều shard song song có thể rút ngắn thời gian đồng hồ nhưng tổng CPU-minute, database load và chi phí runner lại tăng.

Ví dụ, một suite mất 40 phút khi chạy tuần tự có thể hoàn thành trong 12 phút khi dùng nhiều runner. Tuy nhiên, nếu mỗi runner khởi tạo database riêng và tải lại toàn bộ fixture lớn, tổng chi phí có thể tăng mạnh. Cần tối ưu cả thời gian phản hồi, độ ổn định và chi phí tài nguyên.

## 2. Xác định mục tiêu thời gian chạy và ngân sách kiểm thử

### Đặt mục tiêu theo vòng phản hồi

Không phải mọi thay đổi đều cần cùng độ sâu kiểm tra ở cùng thời điểm. Có thể xác định các mục tiêu:

| Vòng kiểm thử | Mục tiêu thời gian | Phạm vi điển hình |
|---|---|---|
| Phản hồi tại máy phát triển | Rất ngắn | Test đơn vị và kiểm tra tập trung |
| Pull request | Ngắn, đủ để quyết định review | Unit, component, contract và smoke test liên quan |
| Sau tích hợp | Trung bình | Integration và hồi quy theo tác động |
| Trước phát hành | Dài hơn, ưu tiên độ bao phủ | Bộ hồi quy rộng, E2E quan trọng, phi chức năng theo rủi ro |
| Theo lịch | Có thể kéo dài | Full regression, kiểm tra tương thích, hiệu năng và dữ liệu lớn |

Các mốc thời gian phải dựa trên quy mô hệ thống, yêu cầu phát hành và năng lực CI. Không dùng một ngưỡng chung cho mọi tổ chức.

### Lập ngân sách thời gian cho từng suite

Tách tổng thời gian thành các phần để biết nơi cần tối ưu:

- Khởi tạo runner và tải dependency.
- Chuẩn bị môi trường, schema và fixture.
- Thời gian thực thi test.
- Thời gian chờ bất đồng bộ và phụ thuộc ngoài.
- Thu thập artifact và báo cáo.
- Cleanup và reset.
- Thời gian xếp hàng chờ runner.

Nếu pipeline mất 20 phút nhưng test chỉ thực thi 6 phút, tối ưu assertion hoặc code test có thể không đem lại nhiều lợi ích. Nút thắt có thể nằm ở provisioning, image download, seed dữ liệu hoặc hàng đợi runner.

### Đặt ngân sách theo mức ưu tiên

Mỗi vòng nên có ngân sách và quy tắc vượt ngưỡng:

- Nhóm test chặn pull request cần ổn định và có thời gian dự đoán được.
- Nhóm test tác động rộng có thể chạy sau khi tích hợp.
- Test dài hoặc tốn tài nguyên có thể chạy theo lịch hoặc trước mốc phát hành.
- Test bắt buộc về bảo mật, dữ liệu hoặc nghĩa vụ không được bỏ chỉ để đáp ứng thời gian.
- Khi ngân sách bị vượt, phân tích nguyên nhân trước khi giảm phạm vi.

Không cắt test có rủi ro cao chỉ vì chúng chậm. Cần xem xét cải thiện cấp test, dữ liệu, môi trường hoặc kiến trúc trước khi thay đổi chính sách.

### Đo phân vị và xu hướng

Thời gian trung bình có thể che giấu những lần chạy rất chậm. Theo dõi p50, p90 hoặc p95 cho thời gian pipeline và từng suite. Đo riêng:

- Thời gian chờ runner.
- Thời gian setup dữ liệu.
- Thời gian thực thi.
- Thời gian cleanup.
- Tỷ lệ timeout.
- Tỷ lệ test retry hoặc flaky.
- Tổng tài nguyên sử dụng.

So sánh theo loại thay đổi, nhánh, môi trường và kích thước dataset để tìm xu hướng có thể hành động.

## 3. Tổ chức các lớp kiểm thử theo phạm vi và thời điểm

### Lớp phản hồi nhanh

Lớp này thường gồm unit test, kiểm tra component nhẹ và một số contract test. Mục tiêu là phát hiện lỗi cục bộ sớm, với dữ liệu nhỏ và phụ thuộc được cô lập.

Yêu cầu thường gặp:

- Chạy nhanh và ổn định.
- Không cần môi trường dùng chung.
- Fixture nhỏ, dễ tạo lại.
- Có thể chạy song song cao.
- Lỗi chỉ rõ module và điều kiện gây sai.

Lớp này không thay thế integration hoặc E2E. Một unit test tính đúng tổng tiền không chứng minh dịch vụ thanh toán và database phối hợp đúng.

### Lớp hồi quy theo tác động

Sau khi xác định thành phần bị thay đổi, chạy các test gắn với thành phần, API, yêu cầu và hành trình liên quan. Lớp này cần sử dụng bản đồ phụ thuộc và truy vết.

Ví dụ, thay đổi schema đơn hàng có thể yêu cầu:

- Test migration và mapping.
- Test API đọc/ghi đơn hàng.
- Contract test với service lập hóa đơn.
- Test worker xử lý sự kiện đơn hàng.
- E2E tạo, cập nhật và hủy đơn ở những nhánh có rủi ro.

Không chỉ chọn test nằm trong cùng thư mục với tệp đã sửa. Tác động có thể đi qua interface, schema, event hoặc cấu hình.

### Lớp hồi quy rộng

Lớp rộng bao gồm các hành trình quan trọng và các khu vực có thể bị ảnh hưởng gián tiếp. Chạy sau tích hợp, trước phát hành hoặc theo lịch tùy mức rủi ro.

Nên bao gồm:

- Luồng nghiệp vụ cốt lõi.
- Phân quyền và phân tách tenant.
- Tích hợp quan trọng.
- Migration và tương thích dữ liệu cũ.
- Các nhánh lỗi và phục hồi có hậu quả lớn.
- Kiểm tra nền tảng và cấu hình được hỗ trợ.

### Lớp full regression và kiểm tra theo lịch

Full regression chạy tập hợp rộng nhất đã được định nghĩa cho phiên bản hoặc cấu hình. Nó giúp phát hiện tác động ngoài dự kiến và xác nhận mức bảo vệ tổng thể.

Có thể chạy:

- Theo lịch hàng đêm hoặc hàng tuần.
- Trước release candidate.
- Sau thay đổi nền tảng, dependency hoặc schema lớn.
- Sau một sự cố cho thấy khoảng trống bao phủ.
- Khi thuật toán chọn test bị thay đổi hoặc không đủ tin cậy.

Không nên chỉ dựa vào full regression theo lịch nếu thay đổi có rủi ro cao cần bằng chứng ngay trong pull request.

## 4. Chọn test dựa trên tác động thay đổi

### Xây dựng bản đồ thay đổi đến test

Muốn lựa chọn chính xác, cần liên kết các lớp thông tin:

1. Tệp hoặc thành phần thay đổi.
2. Module, API, schema, event hoặc cấu hình liên quan.
3. Yêu cầu và quy tắc nghiệp vụ bị tác động.
4. Rủi ro phát sinh.
5. Test có thể phát hiện lỗi ở vùng đó.
6. Mức độ tin cậy và thời điểm cập nhật của liên kết.

Nguồn ánh xạ có thể là metadata trong test, tag, code ownership, dependency graph, contract registry, traceability matrix hoặc phân tích phụ thuộc mã. Có thể kết hợp nhiều nguồn thay vì dựa vào một heuristic duy nhất.

### Dùng đồ thị phụ thuộc

Đồ thị phụ thuộc thể hiện thành phần nào sử dụng thành phần nào. Khi một node thay đổi, nhóm tìm các node ở phía tiêu thụ và các hành trình đi qua chúng.

~~~mermaid
flowchart TD
    A["Thay đổi Order API"] --> B["Order service"]
    B --> C["Order database schema"]
    B --> D["Order event"]
    D --> E["Billing worker"]
    D --> F["Notification worker"]
    C --> G["Order read API"]
    E --> H["Invoice API"]
    F --> I["Email sink"]
    G --> J["Order E2E"]
    H --> K["Billing integration test"]
    I --> L["Notification contract test"]
~~~

Sơ đồ chỉ minh họa. Đồ thị thực tế cần biểu diễn cả phụ thuộc runtime, dữ liệu, hợp đồng và cấu hình. Một thư viện dùng chung hoặc schema có thể ảnh hưởng rộng hơn quan hệ import trong mã nguồn.

### Chọn theo độ sâu tác động

Có thể dùng các vòng lân cận:

- **Trực tiếp:** test cho module hoặc hành vi được sửa.
- **Một ranh giới:** test consumer, provider, API hoặc schema liên quan.
- **Hành trình:** test nghiệp vụ đi qua các thành phần bị ảnh hưởng.
- **Toàn hệ thống:** test rộng khi thay đổi nền tảng, xác thực, cấu hình hoặc thành phần dùng chung.

Độ sâu cần dựa trên mức rủi ro. Thay đổi CSS cục bộ có thể cần một số kiểm tra giao diện; thay đổi thư viện mã hóa hoặc phân quyền có thể cần mở rộng đến nhiều dịch vụ.

### Dùng test impact analysis có kiểm soát

Test impact analysis (TIA) dùng thông tin thay đổi và quan hệ giữa mã với test để đề xuất tập test phù hợp. Có thể dựa trên:

- Lịch sử test đã thực thi và tệp được chạm tới.
- Quan hệ coverage giữa test và mã.
- Dependency graph.
- Tag theo module, feature hoặc risk.
- Traceability từ yêu cầu đến test.
- Metadata do nhóm duy trì.

TIA có thể bỏ sót khi test không ghi nhận đầy đủ coverage, mã sinh tự động, reflection, cấu hình động hoặc hành vi phụ thuộc dữ liệu. Do đó:

- Đo tỷ lệ lỗi mà tập test chọn được phát hiện so với full regression.
- Kiểm tra lại ánh xạ khi cấu trúc module thay đổi.
- Mở rộng phạm vi khi dữ liệu đầu vào thiếu hoặc phân tích không chắc chắn.
- Chạy full regression theo lịch để tìm lỗi ngoài dự đoán.
- Ghi lại lý do test được chọn hoặc loại khỏi vòng hiện tại.

### Xử lý thay đổi không dễ ánh xạ

Một số thay đổi có tác động rộng hoặc khó xác định:

- File cấu hình chung.
- Dependency hoặc runtime.
- Migration database.
- Hệ thống xác thực và phân quyền.
- Thư viện logging, serialization hoặc networking.
- Feature flag và quy tắc định tuyến.
- Hạ tầng build, container hoặc pipeline.

Đối với nhóm này, dùng chính sách mở rộng phạm vi được xác định trước. Ví dụ, thay đổi schema có thể yêu cầu test migration, consumer và dữ liệu cũ; thay đổi authentication có thể yêu cầu nhiều hành trình và vai trò.

## 5. Quản lý dữ liệu cho các vòng kiểm thử tăng dần

### Phân biệt dữ liệu dùng chung và dữ liệu riêng

Dữ liệu dùng chung có thể giảm chi phí tạo nhưng phải bất biến hoặc được bảo vệ. Dữ liệu riêng giúp test độc lập và chạy song song.

| Phạm vi dữ liệu | Cách sử dụng | Yêu cầu |
|---|---|---|
| Seed nền | Danh mục hoặc cấu hình chuẩn | Có phiên bản, bất biến trong lúc chạy |
| Fixture suite | Dữ liệu được nhiều test chỉ đọc | Có chủ sở hữu và reset theo suite |
| Fixture test | Tài khoản, đơn hàng hoặc trạng thái riêng | Tạo và cleanup theo test |
| Dataset performance | Dữ liệu lớn, có phân bố xác định | Seed, kích thước và snapshot được ghi lại |
| Dataset migration | Dữ liệu đại diện cho phiên bản schema cũ | Có thể khôi phục và xác minh sau migration |
| Dataset điều tra | Dữ liệu tái hiện lỗi | Giữ có giới hạn theo retention |

Không cho phép test sửa dữ liệu dùng chung mà không có cơ chế cô lập. Nếu test cần thay đổi một bản ghi nền, tạo bản sao riêng cho test hoặc dùng transaction/schema độc lập.

### Tạo dữ liệu theo run ID và test ID

Mỗi lần chạy cần có định danh để tránh xung đột:

- Prefix tên tenant, tài khoản và tài nguyên.
- UUID hoặc ID riêng cho test.
- Namespace cache và object storage.
- Schema hoặc database riêng theo worker nếu phù hợp.
- Queue hoặc subscription riêng khi cần.
- External reference ID cho sandbox.

Run ID cần xuất hiện trong log, registry tài nguyên và báo cáo. Không đưa token, mật khẩu hoặc dữ liệu cá nhân vào ID.

### Tái sử dụng dữ liệu nền một cách an toàn

Tái sử dụng seed hoặc snapshot có thể giảm thời gian setup, đặc biệt với dataset lớn. Cần bảo đảm:

- Snapshot được tạo từ nguồn đáng tin cậy.
- Có phiên bản schema và checksum.
- Không chứa dữ liệu production nhạy cảm.
- Có thể restore vào môi trường cô lập.
- Test không sửa snapshot gốc.
- Có quy trình nâng cấp khi migration thay đổi.
- Kết quả vẫn được xác minh sau khi khôi phục.

Một snapshot nhanh nhưng cũ có thể khiến test chạy trên cấu trúc dữ liệu không còn đại diện. Phải gắn snapshot với phiên bản và thời hạn hiệu lực.

### Chọn chiến lược dữ liệu theo cấp test

- Unit test: dữ liệu trong bộ nhớ và builder nhỏ.
- Component test: database hoặc container riêng, seed tối thiểu.
- Integration test: fixture có quan hệ và dữ liệu phụ thuộc thật.
- E2E: dữ liệu được tạo qua API setup hoặc hành trình có kiểm soát.
- Performance test: dataset lớn, có phân bố và seed ổn định.
- Migration test: snapshot từ schema cũ, chạy migration và kiểm tra invariant.
- Resilience test: dữ liệu có thể đối soát sau restart, failover hoặc retry.

Không cần tạo toàn bộ dataset E2E cho mỗi unit test. Dữ liệu cần vừa đủ để kiểm tra mục tiêu, đồng thời giữ được tính đại diện.

## 6. Chọn chiến lược reset, cleanup và thời hạn tồn tại

### Reset theo phạm vi chạy

Các cách reset thường dùng:

| Cách reset | Phù hợp khi | Hạn chế |
|---|---|---|
| Transaction rollback | Test dùng một kết nối và không có tác dụng phụ ngoài transaction | Không bao phủ message hoặc service khác |
| Xóa theo namespace | Nhiều run dùng chung hạ tầng nhưng có dữ liệu riêng | Cần ghi nhận mọi tài nguyên đã tạo |
| Database/schema riêng | Cần cô lập mạnh hoặc chạy song song | Tốn thời gian và tài nguyên |
| Restore snapshot | Dataset lớn và cần trạng thái chuẩn | Phụ thuộc snapshot đúng phiên bản |
| Re-seed | Dataset nhỏ hoặc thay đổi có kiểm soát | Có thể chậm nếu seed lớn |

Chọn cách reset theo ranh giới dữ liệu. Có thể dùng rollback cho database và cleanup theo run ID cho queue, file hoặc dịch vụ ngoài.

### Cleanup theo registry tài nguyên

Khi test tạo nhiều tài nguyên, ghi chúng vào registry theo run ID. Registry nên có:

- Loại tài nguyên và ID.
- Môi trường và namespace.
- Chủ sở hữu hoặc suite tạo.
- Thời điểm tạo và expiresAt.
- Trạng thái cleanup.
- Quan hệ phụ thuộc nếu cần.
- Dấu vết lỗi cleanup.

Cleanup chỉ xóa tài nguyên thuộc run hiện tại. Khi runner bị dừng, một janitor có thể đọc registry và xử lý tài nguyên quá hạn.

### Đặt TTL và retention

TTL cần đủ dài cho test, retry và điều tra, nhưng giới hạn tuổi dữ liệu. Phân biệt:

- Hết hiệu lực nghiệp vụ.
- Thời điểm xóa vật lý.
- Thời hạn giữ artifact.
- Retention bắt buộc của audit hoặc sự kiện.

Không dùng TTL chung cho mọi loại dữ liệu. Message có thể cần giữ theo retention queue; screenshot pass có thể chỉ cần lưu ngắn; artifact fail có thể cần thời hạn dài hơn nhưng vẫn có giới hạn.

### Dọn dẹp không làm mất bằng chứng

Khi test fail, giữ những ID, log, trace hoặc fixture cần để tái hiện trong thời hạn đã định. Không xóa ngay dữ liệu đang cần đối soát. Sau khi điều tra, cleanup tài nguyên theo chính sách và xác minh không còn tác dụng phụ treo.

Nếu cleanup thất bại, báo cáo cần ghi tài nguyên còn lại, lý do, người sở hữu và cách xử lý. Không coi lệnh xóa trả thành công là bằng chứng duy nhất rằng môi trường đã sạch.

## 7. Tối ưu thời gian chạy mà vẫn giữ chất lượng bằng chứng

### Phân tích thời gian từng bước

Đo thời gian theo test và theo giai đoạn:

- Provision runner.
- Tải dependency và image.
- Khởi tạo dịch vụ.
- Tạo hoặc restore dữ liệu.
- Thực thi test.
- Chờ tác vụ bất đồng bộ.
- Thu thập artifact.
- Cleanup.

Dùng dữ liệu đo để ưu tiên tối ưu phần chiếm nhiều thời gian hoặc có biến động lớn. Tránh tối ưu một test nhanh trong khi setup toàn suite mất phần lớn thời gian.

### Chạy song song và chia shard

Có thể chia suite thành shard theo thời gian chạy, module, loại test hoặc tài nguyên. Để phân phối tốt:

- Dùng thời gian thực thi lịch sử để cân bằng shard.
- Tránh một shard chứa tất cả test E2E dài.
- Giới hạn concurrency theo năng lực database và sandbox.
- Dùng namespace riêng cho mỗi shard.
- Xác minh test an toàn khi chạy song song.
- Theo dõi thời gian shard chậm nhất, không chỉ tổng trung bình.

Một shard bị quá tải có thể kéo dài toàn pipeline dù các shard khác hoàn thành sớm. Cân bằng theo thời gian và tài nguyên thực tế.

### Sắp xếp test theo giá trị phản hồi

Trong một vòng, có thể ưu tiên:

1. Test nhanh cho vùng thay đổi trực tiếp.
2. Test có khả năng phát hiện lỗi nghiêm trọng.
3. Contract và integration test ở ranh giới bị ảnh hưởng.
4. Hành trình E2E đại diện.
5. Test dài hoặc ít rủi ro hơn.

Thứ tự này giúp lỗi quan trọng được phát hiện sớm. Tuy nhiên, không được bỏ test ở cuối vòng nếu chúng là điều kiện bắt buộc của cổng chất lượng. Sắp xếp chỉ thay đổi thứ tự phản hồi, không tự thay đổi phạm vi đã cam kết.

### Giảm chi phí setup và teardown

Các biện pháp có thể gồm:

- Dùng fixture bất biến cho dữ liệu chỉ đọc.
- Restore snapshot theo worker.
- Tạo nhiều đối tượng trong một batch khi API hỗ trợ.
- Chỉ seed dữ liệu cần cho tập test.
- Dùng container hoặc process tái sử dụng an toàn.
- Cleanup theo namespace thay vì quét toàn môi trường.
- Thu thập artifact theo chính sách, tránh sao chép log không cần thiết.

Không tái sử dụng trạng thái có thể thay đổi chỉ để giảm thời gian. Tối ưu setup phải giữ được tính độc lập và tái lập.

### Cache kết quả kiểm thử có điều kiện

Một số bước build, dependency hoặc test có thể tái sử dụng kết quả nếu đầu vào không thay đổi. Cache cần có khóa dựa trên các yếu tố ảnh hưởng kết quả:

- Commit hoặc hash đầu vào.
- Phiên bản toolchain và dependency.
- Cấu hình, feature flag và môi trường.
- Seed, fixture hoặc snapshot.
- Phiên bản test và dữ liệu phụ thuộc.

Nếu khóa cache thiếu một đầu vào quan trọng, kết quả cũ có thể bị dùng cho thay đổi mới. Không cache kết quả của test phụ thuộc trạng thái bên ngoài biến động nếu không thể chứng minh tính hợp lệ.

### Không tối ưu bằng cách che giấu lỗi

Các cách làm sau làm giảm chất lượng bằng chứng:

- Bỏ test chậm nhưng quan trọng mà không có đánh giá rủi ro.
- Retry cho đến khi pass và chỉ lưu kết quả cuối.
- Dùng dữ liệu dùng chung khiến test nhanh nhưng phụ thuộc thứ tự.
- Tăng timeout vô hạn thay vì xác định trạng thái bất đồng bộ.
- Bỏ assertion để giảm thời gian.
- Cache kết quả mà không kiểm tra đầy đủ đầu vào.

Mọi tối ưu cần đo cả tốc độ, độ ổn định và khả năng phát hiện lỗi.

## 8. Xử lý test thất bại, flaky và retry trong chiến lược tăng dần

### Giữ lại kết quả ban đầu

Khi một test thất bại, cần giữ trạng thái lần chạy đầu, log, trace, seed và metadata. Nếu retry, báo cáo phải phân biệt:

- Fail lần đầu.
- Pass hoặc fail ở từng lần retry.
- Nguyên nhân được xác định hay chưa.
- Tác dụng phụ có thể đã xảy ra trước retry hay không.

Không để một lần retry thành công biến kết quả tổng thể thành xanh mà không có giải thích.

### Phân biệt lỗi sản phẩm với lỗi môi trường

Phân loại theo bằng chứng:

- Lỗi sản phẩm: hành vi hoặc dữ liệu vi phạm yêu cầu.
- Lỗi test: setup, fixture, assertion hoặc harness sai.
- Lỗi môi trường: runner, tài nguyên hoặc cấu hình không sẵn sàng.
- Lỗi phụ thuộc: sandbox hoặc nhà cung cấp gặp vấn đề.
- Flaky: kết quả thay đổi trong điều kiện tương đương mà chưa có nguyên nhân ổn định.
- Bị chặn: thiếu quyền hoặc dữ liệu để thực thi.

Nếu không đủ bằng chứng, giữ trạng thái chưa xác định và mở rộng điều tra. Không tự gán timeout là lỗi môi trường.

### Cách ly có thời hạn

Một test flaky có thể được cách ly tạm thời nếu có biện pháp bù và người chịu trách nhiệm. Bản ghi cần có:

- ID test và vùng rủi ro bị giảm bảo vệ.
- Lý do cách ly và bằng chứng.
- Người sở hữu.
- Thời hạn sửa.
- Bộ kiểm thử thay thế hoặc kiểm soát bù.
- Điều kiện đưa test trở lại.

Không để test quan trọng bị cách ly vô thời hạn. Nếu không có kiểm soát bù, việc cách ly có thể làm mất bảo vệ hồi quy.

## 9. Đưa chiến lược tăng dần vào pipeline

### Pipeline mẫu

Một pipeline có thể chia thành các stage:

~~~mermaid
flowchart TD
    A["Thay đổi mã, schema hoặc cấu hình"] --> B["Phân tích tác động"]
    B --> C["Chọn test liên quan và kiểm tra độ tin cậy của ánh xạ"]
    C --> D["Unit / Component / Contract"]
    D --> E{"Kết quả đạt?"}
    E -->|Không| F["Báo lỗi và giữ bằng chứng"]
    E -->|Có| G["Integration và E2E theo rủi ro"]
    G --> H{"Rủi ro hoặc thay đổi rộng?"}
    H -->|Có| I["Mở rộng regression"]
    H -->|Không| J["Review và tích hợp"]
    I --> K["Full regression theo lịch hoặc trước phát hành"]
    J --> K
~~~

Sơ đồ là một cấu hình tham khảo. Điều kiện mở rộng phải được định nghĩa rõ, chẳng hạn thay đổi shared library, schema, authentication hoặc TIA có độ tin cậy thấp.

### Quy định cổng chất lượng

Mỗi stage cần có điều kiện pass/fail và điều kiện mở rộng:

- Test bắt buộc liên quan phải chạy và đạt.
- Test bị skip hoặc bị chặn phải hiển thị rõ.
- Phân tích tác động phải có mức tin cậy.
- Thay đổi rộng hoặc rủi ro cao kích hoạt bộ test mở rộng.
- Migration cần kiểm tra trên dữ liệu cũ và mới.
- Artifact lỗi phải có thể truy vết.
- Cách ly test flaky phải có quyết định và thời hạn.
- Full regression cần chạy theo lịch và trước các mốc đã xác định.

Không để công cụ TIA tự động loại bỏ test bắt buộc mà không có quy tắc fallback.

### Quy định khi TIA không khả dụng

Nếu phân tích tác động lỗi, thiếu metadata hoặc không thể xây dựng dependency graph, pipeline cần có hành vi mặc định an toàn, ví dụ:

- Chạy tập hồi quy rộng hơn.
- Chạy nhóm test theo module có liên quan.
- Chặn merge nếu thay đổi thuộc vùng rủi ro cao.
- Yêu cầu người review xác định phạm vi bổ sung.

Không coi “không tìm thấy test liên quan” là bằng chứng rằng không cần test.

## 10. Ví dụ: bộ hồi quy cho hệ thống thương mại điện tử

Giả sử hệ thống có các module catalog, cart, order, payment, inventory và notification. Một pull request thay đổi cách tính tổng tiền đơn hàng và thêm trường giảm giá.

### Phân tích tác động

Nhóm xác định:

- Module trực tiếp: order pricing.
- Schema: trường discount trên order item.
- Phụ thuộc: tax calculation, payment request, invoice.
- Hành trình: tạo giỏ, áp mã, thanh toán và xem hóa đơn.
- Rủi ro: tính sai tiền, làm tròn sai, callback không khớp số tiền, migration dữ liệu cũ.

### Chọn test theo từng vòng

| Vòng | Test được chọn | Lý do |
|---|---|---|
| Tại máy phát triển | Unit test công thức giá và biên giảm giá | Phản hồi nhanh cho logic trực tiếp |
| Pull request | Unit, component, contract payment và migration test | Kiểm tra ranh giới và dữ liệu |
| Sau tích hợp | E2E áp mã, thanh toán sandbox, hủy đơn và hoàn tiền liên quan | Xác minh hành trình xuyên thành phần |
| Trước phát hành | Regression rộng về order, invoice, inventory và quyền | Phát hiện tác động gián tiếp |
| Theo lịch | Full regression với dataset và cấu hình nền tảng | Tìm lỗi ngoài phạm vi lựa chọn |

### Quản lý dữ liệu

- Seed catalog chỉ đọc có phiên bản.
- Tạo cart, order và payment riêng theo run ID.
- Dùng fixture giá trị biên cho giảm giá và thuế.
- Dataset migration có bản ghi theo schema cũ.
- Mỗi shard có namespace riêng.
- Cleanup đơn hàng và giao dịch sandbox theo registry.
- TTL giới hạn dữ liệu test còn sót.
- Giữ artifact thất bại trong thời hạn điều tra.

### Đánh giá kết quả

Nếu TIA chỉ chọn unit test giá mà bỏ qua contract payment, nhóm cần kiểm tra vì sao ánh xạ phụ thuộc chưa bao gồm consumer. Nếu migration test không có dữ liệu cũ, cần bổ sung snapshot trước khi kết luận. Nếu E2E fail do sandbox timeout, giữ kết quả lần đầu và xác minh giao dịch trước khi retry để tránh tạo thanh toán trùng.

Ví dụ cho thấy lựa chọn tăng dần phải nối tác động mã với rủi ro nghiệp vụ và dữ liệu thực tế.

## 11. Đo lường hiệu quả và điều chỉnh chiến lược

### Chỉ số về tốc độ và tài nguyên

Theo dõi:

- Thời gian từ commit đến phản hồi đầu tiên.
- Thời gian pull request pipeline p50/p95.
- Thời gian full regression.
- Thời gian setup và cleanup dữ liệu.
- Thời gian chờ runner.
- CPU-minute hoặc chi phí runner.
- Mức sử dụng database, broker và sandbox.
- Chênh lệch thời gian giữa shard nhanh nhất và chậm nhất.

Các chỉ số này giúp xác định tối ưu nào thực sự giảm thời gian hoặc chi phí.

### Chỉ số về chất lượng lựa chọn

Đo:

- Tỷ lệ test được chọn có liên quan đến thay đổi.
- Tỷ lệ lỗi hồi quy được phát hiện bởi vòng incremental.
- Lỗi chỉ được phát hiện ở full regression hoặc sau phát hành.
- Tỷ lệ thay đổi cần mở rộng vì TIA thiếu tin cậy.
- Mức bao phủ của dependency graph và traceability.
- Tỷ lệ test bị skip, bị chặn hoặc cách ly.
- Số lỗi do dữ liệu cũ hoặc dữ liệu dùng chung.

Không chỉ đo số test đã bỏ qua. Một chiến lược tốt giảm công việc không cần thiết nhưng vẫn phát hiện lỗi quan trọng sớm.

### Chỉ số về chất lượng dữ liệu

Có thể theo dõi:

- Thời gian tạo và reset fixture.
- Tỷ lệ setup/cleanup thành công.
- Số tài nguyên test tồn tại quá TTL.
- Số lần va chạm dữ liệu giữa run hoặc shard.
- Tỷ lệ test có seed và dữ liệu tái hiện.
- Số lần test phụ thuộc thứ tự.
- Số sự cố do snapshot hoặc seed lỗi thời.

### Rà soát định kỳ

Điều chỉnh chiến lược khi:

- Cấu trúc module hoặc dependency thay đổi.
- Bộ test tăng nhanh hơn năng lực CI.
- Lỗi lọt qua incremental testing tăng.
- Full regression phát hiện nhiều vấn đề mà TIA bỏ sót.
- Dataset lớn hoặc schema thay đổi.
- Tỷ lệ flaky và retry tăng.
- Chi phí runner hoặc môi trường tăng đáng kể.
- Có sự cố cho thấy vùng rủi ro chưa được kiểm tra.

Rà soát nên có đại diện phát triển, kiểm thử, vận hành và chủ sở hữu sản phẩm khi phạm vi ảnh hưởng yêu cầu.

## 12. Những sai lầm thường gặp

- **Chỉ chạy test gần tệp đã sửa:** bỏ qua consumer, schema và hành trình phụ thuộc.
- **Tin tuyệt đối vào TIA:** coverage hoặc dependency metadata có thể thiếu.
- **Không chạy full regression định kỳ:** lỗi ngoài vùng dự đoán có thể tồn tại lâu.
- **Dùng một bộ dữ liệu dùng chung có thể thay đổi:** tạo xung đột và phụ thuộc thứ tự.
- **Tạo lại dataset lớn cho từng test:** tăng thời gian setup không cần thiết.
- **Tái sử dụng snapshot cũ:** test chạy trên schema hoặc dữ liệu không còn đại diện.
- **Chạy song song không cô lập namespace:** test ghi đè hoặc xóa dữ liệu của nhau.
- **Tối ưu thời gian bằng cách bỏ assertion:** giảm khả năng phát hiện lỗi.
- **Cache kết quả thiếu đầu vào:** dùng kết quả cũ cho cấu hình mới.
- **Retry và chỉ giữ kết quả cuối:** che giấu flaky và tác dụng phụ trùng.
- **Không đặt fallback khi phân tích tác động thất bại:** pipeline có thể chọn quá ít test.
- **Để cleanup chạy trước worker:** dữ liệu bị xóa trong khi tác vụ còn xử lý.
- **Chỉ đo thời gian thực thi test:** bỏ qua hàng đợi, provisioning và cleanup.
- **Không quản lý test bị cách ly:** vùng rủi ro mất bảo vệ vô thời hạn.

## 13. Đầu ra cần có trước khi chốt chiến lược hồi quy tăng dần

Một chiến lược đủ dùng nên có:

1. **Danh mục các lớp hồi quy:** mục tiêu, phạm vi và thời điểm chạy.
2. **Ngân sách thời gian:** mục tiêu phản hồi, tổng thời gian và tài nguyên theo stage.
3. **Bản đồ tác động:** liên kết thành phần, schema, API, event, yêu cầu, rủi ro và test.
4. **Quy tắc lựa chọn:** độ sâu phụ thuộc, mức tin cậy TIA và điều kiện mở rộng.
5. **Quy tắc fallback:** hành vi khi phân tích tác động thiếu hoặc lỗi.
6. **Chiến lược dữ liệu:** seed, fixture, snapshot, namespace, reset và cleanup.
7. **Chính sách TTL/retention:** thời hạn dữ liệu và artifact, cách xử lý tài nguyên còn sót.
8. **Thiết kế thực thi:** shard, concurrency, thứ tự test và giới hạn tài nguyên.
9. **Chính sách retry/flaky:** lưu kết quả lần đầu, cách ly có hạn và chủ sở hữu.
10. **Cổng chất lượng:** điều kiện pass/fail, test bắt buộc và stage mở rộng.
11. **Chỉ số theo dõi:** tốc độ, chi phí, chất lượng lựa chọn và chất lượng dữ liệu.
12. **Lịch rà soát:** full regression, thay đổi kiến trúc, sự cố và cập nhật dependency graph.

Trước khi áp dụng, hãy rà soát:

- Mỗi vòng kiểm thử có mục tiêu và ngân sách thời gian rõ không?
- Test được chọn có liên kết với thay đổi, yêu cầu và rủi ro không?
- Thay đổi rộng hoặc không rõ tác động có kích hoạt phạm vi bổ sung không?
- TIA có được đo độ tin cậy và có fallback an toàn không?
- Full regression có lịch chạy và điều kiện kích hoạt rõ không?
- Dữ liệu dùng chung có bất biến và dữ liệu riêng có namespace không?
- Seed, snapshot và migration có phiên bản và có thể tái tạo không?
- Reset, cleanup và TTL có bảo đảm không ảnh hưởng run khác không?
- Chạy song song có giới hạn theo năng lực môi trường không?
- Retry có giữ lại kết quả ban đầu và không che giấu lỗi không?
- Báo cáo có chỉ ra test được chọn, test bị bỏ qua và lý do không?
- Các chỉ số có phản ánh cả tốc độ lẫn khả năng phát hiện lỗi không?

Quản lý thời gian chạy và dữ liệu cho bộ kiểm thử tăng dần giúp nhóm phản hồi nhanh theo thay đổi mà vẫn duy trì bằng chứng hồi quy đáng tin cậy. Hãy kết hợp lựa chọn theo tác động, phân tầng kiểm thử, dữ liệu có vòng đời rõ và một nhánh hồi quy rộng được duy trì thường xuyên. Khi thay đổi kiến trúc, dữ liệu hoặc lịch sử lỗi, cần cập nhật ánh xạ và ngân sách để chiến lược tiếp tục phản ánh đúng rủi ro của sản phẩm.

