# Phân biệt tắt tính năng với quay lui bản triển khai

## Mục tiêu học tập

Sau bài này, người học có thể:

- Phân biệt tắt một tính năng bằng feature flag với quay lui phiên bản ứng dụng đã triển khai.
- Giải thích phạm vi tác động, tốc độ phản ứng và giới hạn của từng biện pháp.
- Chọn cách giảm thiểu sự cố phù hợp khi lỗi chỉ nằm ở một tính năng hoặc ảnh hưởng đến toàn bộ phiên bản.
- Xác định điều kiện để tắt tính năng an toàn, bao gồm đường đi của request, side effect, dependency và dữ liệu.
- Đánh giá khả năng rollback dựa trên artifact, cấu hình, schema và trạng thái dữ liệu hiện tại.
- Thiết kế kill switch, quy trình phê duyệt, audit và xác minh sau khi thay đổi trạng thái.
- Phối hợp feature disable, deployment rollback và data recovery trong một quy trình ứng phó sự cố.

## 1. Hai hành động giải quyết hai phạm vi khác nhau

Khi một release gây ra sự cố, đội ngũ thường có hai lựa chọn được nhắc đến: tắt tính năng mới hoặc quay lui bản triển khai. Hai hành động này có thể cùng giúp giảm tác động, nhưng chúng thay đổi những phần khác nhau của hệ thống.

**Tắt tính năng (feature disable)** thay đổi trạng thái bật/tắt của một khả năng trong ứng dụng. Thường dùng feature flag, kill switch hoặc runtime configuration để ngăn một luồng chức năng được sử dụng trong khi ứng dụng vẫn chạy cùng phiên bản hiện tại.

**Quay lui bản triển khai (deployment rollback)** thay artifact đang chạy bằng một phiên bản đã phát hành trước đó. Hành động này thay đổi code hoặc image được thực thi, có thể đi kèm cấu hình và deployment revision tương ứng.

Ví dụ:

- V2 bổ sung luồng thanh toán mới và luồng này được bật bằng feature flag.
- Sau khi triển khai V2, một lỗi khiến tỷ lệ thanh toán thất bại tăng cao.
- Nếu lỗi chỉ nằm trong luồng thanh toán mới và V2 có đường xử lý cũ còn hoạt động, có thể tắt flag để ngừng luồng mới.
- Nếu lỗi nằm trong thư viện dùng chung làm process tăng memory hoặc mọi request đều chậm, tắt một feature flag có thể không khắc phục được; cần cân nhắc rollback phiên bản.

Tắt tính năng thường có phạm vi hẹp và có thể phản ứng nhanh nếu cấu hình được phân phối tốt. Rollback thay đổi phiên bản đang chạy và có thể giải quyết lỗi ở nhiều phần của release, nhưng thường cần thêm thời gian để triển khai lại, khởi động instance và xác minh.

Nguyên tắc cần nhớ:

> Tắt tính năng ngăn một khả năng cụ thể tiếp tục được sử dụng. Rollback thay đổi phiên bản phần mềm đang chạy. Hãy chọn hành động theo phạm vi lỗi và trạng thái thực tế của hệ thống.

Hai biện pháp không loại trừ nhau. Có thể tắt một tính năng để giảm tác động ngay, sau đó rollback phiên bản nếu cần. Cũng có thể rollback trước rồi giữ một flag ở trạng thái tắt trong lúc điều tra.

## 2. Feature flag là gì?

Feature flag là một cơ chế cho phép ứng dụng quyết định có thực thi một khả năng hay không dựa trên trạng thái cấu hình.

Một flag có thể điều khiển:

- Bật một giao diện mới.
- Chọn thuật toán tính giá.
- Chuyển từ payment provider cũ sang provider mới.
- Cho phép một nhóm người dùng sử dụng tính năng.
- Bật một consumer hoặc background job.
- Chuyển sang implementation mới trong khi vẫn giữ đường xử lý cũ.

Ví dụ logic đơn giản:

~~~java
if (featureFlags.isEnabled("new-checkout", userContext)) {
    return newCheckoutService.checkout(request);
}
return legacyCheckoutService.checkout(request);
~~~

Khi flag tắt, ứng dụng đi theo nhánh cũ. Artifact V2 vẫn đang chạy; chỉ hành vi được chọn tại runtime thay đổi.

Feature flag có thể được đọc từ:

- File cấu hình hoặc environment variable.
- Config service.
- Feature management platform.
- Database hoặc cache.
- Runtime control plane riêng của ứng dụng.

Cách phân phối trạng thái flag ảnh hưởng đến thời gian tắt thực tế. Nếu ứng dụng chỉ đọc flag lúc khởi động, thay đổi flag có thể cần restart. Nếu ứng dụng refresh định kỳ hoặc nhận push update, trạng thái có thể thay đổi khi process đang chạy.

Không nên giả định flag tắt ở giao diện quản trị đồng nghĩa mọi instance đã ngừng tính năng ngay lập tức. Cần đo và xác minh thời gian lan truyền.

## 3. Kill switch là gì và khác feature flag thông thường ra sao?

Kill switch là một loại điều khiển khẩn cấp được thiết kế để vô hiệu hóa nhanh một chức năng hoặc đường xử lý khi xảy ra rủi ro.

Ví dụ:

- Ngừng nhận yêu cầu thanh toán qua provider đang gặp lỗi.
- Tạm dừng gửi email hoặc SMS hàng loạt.
- Ngăn tạo đơn hàng mới trong lúc kiểm tra dữ liệu tồn kho.
- Tắt một background job đang tạo dữ liệu sai.
- Chặn luồng xử lý mới nhưng vẫn cho phép đọc dữ liệu hiện có.

Một feature flag thông thường có thể dùng cho rollout, thử nghiệm hoặc tùy biến theo nhóm người dùng. Kill switch cần có đặc điểm vận hành rõ hơn:

- Có thể thay đổi nhanh khi khẩn cấp.
- Có owner và người được phép kích hoạt.
- Có giá trị mặc định an toàn khi không đọc được cấu hình.
- Có trạng thái và phạm vi áp dụng quan sát được.
- Có audit cho người thay đổi, lý do và thời điểm.
- Có cách xác minh mọi instance đã nhận trạng thái mới.
- Có hướng dẫn khôi phục hoặc bật lại sau khi sự cố được xử lý.

Kill switch không nên là một đường bypass quyền truy cập. Nếu một tính năng bị tắt, API vẫn phải kiểm tra authorization. Không dùng feature flag làm cơ chế duy nhất để bảo vệ dữ liệu hoặc ngăn truy cập trái phép.

Cũng cần phân biệt kill switch với circuit breaker. Circuit breaker tự động ngừng gọi một dependency khi phát hiện lỗi hoặc timeout vượt ngưỡng, sau đó thử phục hồi theo trạng thái half-open. Kill switch thường là quyết định vận hành có chủ đích để vô hiệu hóa một khả năng hoặc đường xử lý. Hai cơ chế có thể phối hợp nhưng mục tiêu và điều kiện kích hoạt khác nhau.

## 4. Deployment rollback là gì?

Deployment rollback là việc đưa môi trường về một artifact hoặc deployment revision trước đó đã được phát hành.

Ví dụ:

~~~text
Trạng thái trước:
  application = V1
  artifact = sha256:old
  config = config-41

Sau release:
  application = V2
  artifact = sha256:new
  config = config-42

Sau deployment rollback:
  application = V1
  artifact = sha256:old
  config = config-41 (nếu tương thích và được chọn khôi phục)
~~~

Rollback có thể bao gồm:

- Triển khai lại container image hoặc package cũ.
- Khôi phục deployment manifest hoặc release revision.
- Chuyển routing về nhóm phiên bản cũ.
- Khôi phục một số cấu hình đã thay đổi cùng release.
- Xác minh phiên bản cũ đang thực sự phục vụ traffic.

Không phải rollback nào cũng tự động khôi phục toàn bộ cấu hình. Có trường hợp chỉ artifact được thay, còn runtime config và feature flags vẫn giữ trạng thái hiện tại. Vì vậy deployment record phải thể hiện rõ artifact và config revision sau rollback.

Rollback phù hợp khi lỗi thuộc phiên bản mới, ảnh hưởng rộng hoặc không thể cô lập bằng flag, và phiên bản cũ vẫn tương thích với schema, dữ liệu và dependency hiện tại.

## 5. So sánh feature disable và deployment rollback

| Tiêu chí | Tắt tính năng | Rollback deployment |
|---|---|---|
| Đối tượng thay đổi | Trạng thái flag hoặc runtime config | Artifact hoặc deployment revision |
| Phạm vi | Thường hẹp, theo feature hoặc cohort | Thường rộng hơn, theo service/release |
| Thời gian phản ứng | Có thể nhanh nếu flag được phân phối động | Phụ thuộc rollout, scheduling và startup |
| Code đang chạy | Vẫn là phiên bản hiện tại | Chuyển về phiên bản cũ |
| Điều kiện tiên quyết | Có flag và đường xử lý an toàn khi tắt | Có artifact cũ và khả năng triển khai lại |
| Tác động lên dữ liệu | Không tự hoàn tác dữ liệu đã ghi | Không tự hoàn tác dữ liệu đã ghi |
| Rủi ro | Nhánh tắt có thể lỗi hoặc flag không lan truyền | Code cũ có thể không tương thích schema/dữ liệu |
| Bằng chứng cần có | Flag revision, trạng thái từng instance, metric theo feature | Artifact digest, deployment ID, config revision, health |
| Trường hợp phù hợp | Lỗi cô lập trong một feature | Lỗi rộng ở code hoặc release |
| Giới hạn | Không loại bỏ code lỗi khỏi process | Có thể cần thời gian và có thể không đảo ngược migration |

Không nên kết luận feature disable luôn an toàn hơn hoặc rollback luôn triệt để hơn. Quyết định phụ thuộc vào lỗi nằm ở đâu, đường fallback có hoạt động không, dữ liệu đã bị thay đổi chưa và phiên bản trước có tương thích không.

## 6. Khi nào nên tắt tính năng?

Tắt tính năng thường là lựa chọn phù hợp khi các điều kiện sau được đáp ứng:

- Lỗi có thể khoanh vùng vào một feature hoặc một nhánh xử lý.
- Có flag được kiểm tra ở đúng ranh giới trước khi thực hiện side effect.
- Nhánh khi flag tắt vẫn hoạt động và đã được kiểm thử.
- Tính năng có thể dừng mà không để lại trạng thái trung gian nguy hiểm.
- Dependency hoặc code dùng chung không phải nguồn gây lỗi.
- Việc tắt không làm mất khả năng thực hiện các thao tác thiết yếu khác.
- Trạng thái flag có thể lan truyền và xác minh đủ nhanh so với mức độ sự cố.

Ví dụ phù hợp:

- Thuật toán tính phí mới cho kết quả sai nhưng thuật toán cũ còn hoạt động.
- Giao diện mới gây lỗi nhưng API cũ vẫn phục vụ được.
- Một provider bên ngoài đang lỗi và có provider dự phòng.
- Một tính năng thử nghiệm gây tăng latency trong một cohort.
- Background job mới tạo event sai và có thể được dừng độc lập.

Tắt flag có thể giúp giảm blast radius ngay trong khi đội ngũ điều tra nguyên nhân hoặc chuẩn bị bản sửa.

## 7. Khi nào nên rollback deployment?

Rollback thường phù hợp khi:

- Lỗi ảnh hưởng đến nhiều endpoint hoặc nhiều feature.
- Một thư viện dùng chung gây crash, memory leak hoặc lỗi bảo mật.
- Startup hoặc process behavior bị hỏng.
- Một thay đổi ở framework hoặc runtime gây lỗi diện rộng.
- Không có flag để cô lập chức năng.
- Đường xử lý khi flag tắt cũng bị ảnh hưởng.
- Có artifact cũ đã được xác minh và tương thích với trạng thái dữ liệu hiện tại.

Ví dụ:

- V2 nâng cấp HTTP client và mọi request ra ngoài đều timeout.
- V2 có lỗi trong connection pool làm cạn tài nguyên.
- Một dependency mới gây lỗi class loading khi ứng dụng khởi động.
- Một thay đổi logging hoặc instrumentation làm tăng tải toàn bộ service.
- Một lỗ hổng bảo mật mới yêu cầu loại bỏ code hoặc dependency khỏi môi trường chạy.

Trong các trường hợp này, tắt một feature flag có thể không loại bỏ được lỗi ở code dùng chung. Rollback hoặc phát hành bản sửa có thể cần thiết.

Tuy nhiên, nếu phiên bản cũ không tương thích schema mới, rollback trực tiếp có thể gây thêm lỗi. Khi đó cần forward fix hoặc một phiên bản tương thích trung gian.

## 8. Khi nào cần phối hợp cả hai?

Có những sự cố cần nhiều lớp phản ứng.

Ví dụ một luồng checkout mới gây ghi sai trạng thái order:

1. Tắt flag checkout mới để ngăn request mới đi vào luồng lỗi.
2. Giữ các chức năng đọc và tra cứu đơn hàng hoạt động.
3. Xác định artifact và config revision đã triển khai.
4. Đánh giá phiên bản cũ có tương thích schema hiện tại không.
5. Nếu tương thích, rollback ứng dụng để loại bỏ code mới.
6. Xác định các đơn hàng đã bị ghi sai và phục hồi có chọn lọc.
7. Xác minh trạng thái nghiệp vụ và event liên quan.
8. Chỉ bật lại feature khi bản sửa đã được kiểm tra.

Trong ví dụ này, feature disable là biện pháp containment nhanh; deployment rollback đưa code về phiên bản đã biết là tốt; data recovery xử lý dữ liệu đã bị ảnh hưởng. Không một hành động nào thay thế hoàn toàn hai hành động còn lại.

## 9. Flag phải nằm đúng ranh giới trước side effect

Một flag chỉ có tác dụng nếu nó được kiểm tra trước khi hệ thống thực hiện hành động cần ngăn.

Ví dụ luồng thanh toán:

~~~mermaid
flowchart TD
    A["Request checkout"] --> B["Kiểm tra authorization"]
    B --> C["Đọc feature flag"]
    C --> D{"New payment enabled?"}
    D -- "Có" --> E["New payment flow"]
    D -- "Không" --> F["Legacy payment flow"]
    E --> G["Gọi payment provider"]
    F --> G
    G --> H["Ghi nhận kết quả"]
~~~

Nếu flag chỉ ẩn nút trên giao diện nhưng API vẫn nhận request và gọi provider, tính năng chưa thực sự được vô hiệu hóa.

Cần kiểm tra flag ở server-side tại các điểm thực hiện side effect:

- API handler hoặc application service.
- Background worker trước khi xử lý job.
- Consumer trước khi thực hiện hành động.
- Scheduler trước khi tạo công việc mới.
- Integration adapter trước khi gọi dịch vụ bên ngoài.

Không nhất thiết phải lặp lại logic flag ở mọi dòng code. Có thể đặt ở ranh giới nghiệp vụ rõ ràng, nhưng cần bảo đảm mọi đường đi vào chức năng đều qua điểm kiểm tra đó.

Nếu có nhiều entry point như HTTP, queue và scheduled job, cần kiểm tra tất cả. Tắt API feature không tự động dừng consumer đang tiếp tục xử lý message đã nằm trong queue.

## 10. Trạng thái flag cần có mặc định an toàn

Khi feature flag service không truy cập được, ứng dụng phải biết nên xử lý thế nào.

Có hai lựa chọn phổ biến:

- **Fail closed:** coi tính năng là tắt khi không xác định được trạng thái. Phù hợp với tính năng có rủi ro cao hoặc side effect nhạy cảm.
- **Fail open:** tiếp tục dùng trạng thái bật hoặc giá trị cache gần nhất. Chỉ phù hợp khi việc tắt có thể gây gián đoạn lớn hơn và rủi ro đã được chấp nhận.

Không có một mặc định đúng cho mọi flag. Cần phân loại theo tác động:

| Loại flag | Hành vi khi không đọc được trạng thái |
|---|---|
| Feature thử nghiệm | Thường tắt hoặc giữ cohort đã được kiểm soát |
| Luồng thanh toán mới | Thường fail closed hoặc fallback sang provider/flow đã xác minh |
| Chức năng thiết yếu | Có thể giữ trạng thái gần nhất nếu tắt gây mất dịch vụ |
| Kill switch bảo vệ an toàn | Cần thiết kế để trạng thái tắt vẫn có thể được kích hoạt và lan truyền đáng tin cậy |
| UI enhancement | Có thể fallback về giao diện cũ |

Nếu dùng cache local, cần xác định thời gian sống tối đa, cách refresh và hành vi khi hết hạn. Cache vô thời hạn có thể khiến một số instance tiếp tục bật feature sau khi operator đã tắt flag.

Với kill switch, nên có cơ chế kiểm tra trạng thái và xác nhận đã áp dụng ở tất cả instance. Không nên chỉ dựa vào một thông báo “update successful” từ control plane.

## 11. Thời gian lan truyền và trạng thái không đồng nhất

Trong hệ thống nhiều instance, flag có thể được cập nhật ở control plane nhưng các process nhận trạng thái ở thời điểm khác nhau.

Nguyên nhân:

- Polling interval.
- Push notification bị mất.
- Local cache chưa refresh.
- Network partition.
- Instance đang mất kết nối với config service.
- Background worker dùng config được tải lúc khởi động.
- Một region hoặc cluster chưa nhận revision mới.

Do đó, cần quan sát:

- Flag revision hiện tại ở control plane.
- Revision mà mỗi instance đang sử dụng.
- Thời điểm instance nhận cấu hình.
- Tỷ lệ request vẫn đi vào nhánh feature sau khi tắt.
- Worker hoặc consumer nào còn xử lý công việc cũ.
- Instance nào chưa xác nhận trạng thái.

Với sự cố nghiêm trọng, có thể cần drain hoặc restart instance chưa nhận flag mới, hoặc tạm dừng consumer và scheduler. Đây là quyết định vận hành dựa trên bằng chứng; không nên giả định tất cả instance đã cập nhật ngay lập tức.

## 12. Tắt feature không đảo ngược dữ liệu hoặc side effect

Đây là giới hạn quan trọng nhất của feature disable.

Giả sử feature mới đã:

- Tạo đơn hàng.
- Trừ tồn kho.
- Gửi event lên message broker.
- Gửi email cho khách hàng.
- Gọi payment provider.
- Ghi dữ liệu theo schema mới.

Tắt flag chỉ ngăn các lần thực thi tiếp theo đi vào nhánh đó. Nó không xóa đơn hàng đã tạo, không tự hoàn lại tồn kho, không thu hồi email đã gửi và không hủy giao dịch thanh toán.

Cần phân biệt:

- Ngăn side effect mới.
- Xác định side effect đã xảy ra.
- Bù trừ hoặc phục hồi các side effect đó.
- Xác minh trạng thái cuối cùng.

Ví dụ, nếu một feature đã tạo giao dịch thanh toán trùng, tắt feature sẽ ngăn các lần thanh toán trùng tiếp theo. Những giao dịch đã tạo cần được đối chiếu với payment provider và xử lý hoàn tiền hoặc hủy theo nghiệp vụ.

Không dùng delete trực tiếp để xóa lịch sử giao dịch nhằm làm cho dữ liệu “trông như chưa từng xảy ra”. Với nghiệp vụ tài chính, cần giữ audit và dùng compensating transaction phù hợp.

## 13. Tắt feature không đồng nghĩa loại bỏ code lỗi hoặc lỗ hổng

Một feature flag có thể ngăn một nhánh code được gọi trong điều kiện bình thường, nhưng code vẫn nằm trong artifact và process.

Nếu lỗi là:

- Dependency có lỗ hổng và được load khi khởi động.
- Một parser dùng chung có thể bị khai thác qua endpoint khác.
- Một background thread vẫn chạy dù UI feature đã tắt.
- Code dùng chung có memory leak.
- Một API endpoint vẫn có thể gọi trực tiếp mà không qua UI.
- Một module có side effect trước khi kiểm tra flag.

Thì chỉ tắt flag có thể không loại bỏ rủi ro.

Đối với sự cố bảo mật, cần xác định đường khai thác và mọi entry point. Nếu code hoặc dependency bị xâm phạm vẫn được nạp hoặc truy cập được, cần phát hành bản sửa hoặc rollback artifact theo chính sách bảo mật.

Feature flag cũng không thay thế authorization, input validation hoặc access control. Không nên dựa vào trạng thái flag để bảo vệ một tài nguyên nhạy cảm.

## 14. Deployment rollback cũng có giới hạn

Rollback deployment không phải nút đưa toàn hệ thống về quá khứ.

Các vấn đề cần đánh giá:

- Phiên bản cũ có tương thích schema hiện tại không?
- Migration đã xóa hoặc chuyển đổi dữ liệu chưa?
- Feature flag và runtime config có cần khôi phục riêng không?
- Secret version cũ còn hiệu lực không?
- Message hoặc event do phiên bản mới phát ra đã được xử lý chưa?
- Artifact cũ có còn trong registry và đã được xác minh không?
- Dependency hoặc hạ tầng bên ngoài có thay đổi không?
- Phiên bản cũ có tương thích với API của dependency hiện tại không?

Nếu phiên bản mới đã chạy migration phá hủy, deployment rollback có thể làm ứng dụng cũ không khởi động hoặc ghi sai dữ liệu.

Nếu lỗi chỉ nằm ở một feature, rollback toàn bộ service có thể làm mất các bản sửa hữu ích khác hoặc gây downtime không cần thiết. Cần so sánh phạm vi lỗi với phạm vi rollback.

## 15. Quy trình ứng phó sự cố

Khi phát hiện lỗi sau deploy, có thể dùng quy trình sau:

1. **Containment:** giảm tác động tức thời bằng cách tắt flag, dừng consumer, tạm dừng job hoặc hạn chế traffic nếu phù hợp.
2. **Classify:** xác định lỗi thuộc feature, code dùng chung, dependency, config, schema hay dữ liệu.
3. **Measure:** xem metric theo version, feature, cohort và endpoint.
4. **Check compatibility:** xác định code cũ có thể chạy với schema và dữ liệu hiện tại không.
5. **Choose action:** giữ phiên bản hiện tại và sửa flag, rollback deployment hoặc phát hành forward fix.
6. **Recover state:** xử lý dữ liệu hoặc side effect đã xảy ra nếu cần.
7. **Verify:** xác nhận flag revision, artifact digest, instance health và business invariant.
8. **Communicate and record:** lưu quyết định, người thực hiện, mốc thời gian và phạm vi ảnh hưởng.
9. **Re-enable carefully:** chỉ bật lại feature sau khi bản sửa được kiểm tra và rollout có kiểm soát.

~~~mermaid
flowchart TD
    A["Phát hiện lỗi sau deploy"] --> B["Contain tác động"]
    B --> C["Phân loại: feature hay release-wide?"]
    C --> D{"Có thể cô lập bằng flag an toàn?"}
    D -- "Có" --> E["Tắt feature / kill switch"]
    E --> F["Xác minh flag đã lan truyền"]
    F --> G["Đánh giá dữ liệu và side effects"]
    D -- "Không" --> H["Đánh giá rollback compatibility"]
    H --> I{"Artifact cũ tương thích?"}
    I -- "Có" --> J["Rollback deployment"]
    I -- "Không" --> K["Forward fix / bản tương thích"]
    G --> L["Recover hoặc compensate nếu cần"]
    J --> M["Verify toàn hệ thống"]
    K --> M
    L --> M
    M --> N["Ghi audit và theo dõi"]
~~~

Trong sự cố thực tế, các nhánh có thể phối hợp. Ví dụ tắt flag trước để ngừng request mới, rồi rollback ứng dụng và phục hồi các bản ghi đã bị ảnh hưởng.

## 16. Ví dụ: tắt luồng thanh toán mới

Một dịch vụ checkout triển khai V2 với luồng thanh toán mới. Feature flag được bật cho 10% người dùng. Sau 15 phút, metric cho thấy tỷ lệ payment timeout của cohort mới tăng rõ rệt; cohort dùng luồng cũ vẫn ổn định.

Đội ngũ cần:

1. Tắt flag new-payment-flow.
2. Xác nhận tất cả API instance đã nhận flag revision mới.
3. Kiểm tra background worker và retry queue có tiếp tục gọi provider mới không.
4. Xác nhận request mới được chuyển sang luồng cũ.
5. Đối chiếu payment intent đã tạo trong 15 phút.
6. Kiểm tra provider có giao dịch thành công nhưng callback bị timeout hay không.
7. Reconcile các giao dịch chưa rõ trạng thái, tránh gửi thanh toán trùng.
8. Theo dõi tỷ lệ timeout và tỷ lệ checkout thành công sau khi tắt.
9. Điều tra nguyên nhân và chuẩn bị bản sửa.

Trong tình huống này, rollback toàn bộ V2 có thể chưa cần thiết nếu lỗi chỉ ở luồng mới và code còn lại ổn định. Nhưng nếu V2 cũng thay đổi HTTP client dùng chung khiến cả luồng cũ bị ảnh hưởng, cần cân nhắc rollback hoặc forward fix.

## 17. Ví dụ: lỗi nằm ở runtime dùng chung

Một release nâng cấp thư viện xử lý JSON. Sau deploy, mọi endpoint có payload lớn đều tăng memory và process bị restart. Feature flag chỉ điều khiển giao diện mới, không điều khiển thư viện JSON.

Tắt giao diện mới không ngăn được lỗi vì endpoint cũ cũng dùng thư viện mới. Đội ngũ cần:

1. Dừng rollout để không mở rộng số instance bị ảnh hưởng.
2. Xác định artifact digest và dependency version.
3. Kiểm tra phiên bản trước có tương thích schema và config hiện tại.
4. Nếu tương thích, rollback về artifact cũ theo digest.
5. Xác minh memory, restart count và latency trở lại bình thường.
6. Kiểm tra dữ liệu hoặc request bị xử lý một phần trong thời gian lỗi.
7. Ghi nhận release và điều kiện rollback.
8. Sửa dependency, bổ sung test tải và triển khai lại sau review.

Ví dụ này cho thấy feature disable chỉ phù hợp khi có ranh giới chức năng đủ rõ để cô lập lỗi.

## 18. Quản lý vòng đời feature flag

Feature flag tạo ra thêm trạng thái và nhánh code. Nếu không quản lý, hệ thống có thể tích lũy nhiều flag cũ, gây khó hiểu và làm tăng rủi ro.

Mỗi flag nên có:

- Tên mô tả mục đích.
- Owner chịu trách nhiệm.
- Loại flag: release, experiment, operational hoặc kill switch.
- Giá trị mặc định.
- Phạm vi áp dụng và targeting rule.
- Thời điểm tạo và ngày dự kiến xem xét/xóa.
- Hành vi khi flag service không truy cập được.
- Audit và quyền thay đổi.
- Metric dùng để quan sát tác động.

Khi feature đã ổn định và không còn cần chuyển đổi, nên xóa flag cùng nhánh code cũ trong một thay đổi được review. Không nên để flag luôn tồn tại ở cả hai nhánh trong nhiều năm.

Với kill switch, có thể giữ lâu hơn nếu nó là cơ chế vận hành có giá trị, nhưng cần diễn tập định kỳ và xác nhận owner vẫn phù hợp.

## 19. Kiểm thử feature disable và deployment rollback

Không chỉ kiểm thử đường bật feature. Cần kiểm thử cả đường tắt và cách hệ thống phản ứng khi trạng thái thay đổi giữa lúc đang có request.

Các tình huống nên kiểm tra:

- Flag tắt ngay từ lúc ứng dụng khởi động.
- Flag đổi từ bật sang tắt khi ứng dụng đang chạy.
- Một instance không nhận được config update.
- Flag service mất kết nối.
- Request đang xử lý khi flag đổi trạng thái.
- Job đã nằm trong queue trước khi tắt feature.
- Worker tiếp tục xử lý message cũ.
- Feature fallback sang implementation cũ.
- Code cũ chạy trên schema đã được mở rộng.
- Rollback khi migration đã chạy.
- Rollback trong lúc rollout đang dở.
- Khôi phục routing và xác minh artifact thực tế.

Cần phân biệt request đang chạy tại thời điểm tắt flag với request mới. Flag thường không hủy một transaction hoặc request đã bắt đầu. Nếu cần dừng ngay cả các công việc đang chạy, cần cơ chế cancellation hoặc drain riêng.

## 20. Ví dụ cấu hình vận hành

Một cấu hình minh họa có thể mô tả feature flag và hành động khi có sự cố:

~~~yaml
features:
  new-checkout:
    enabled: false
    owner: checkout-team
    default_on_error: false
    evaluation_scope: server
    reviewed_at: 2026-11-18

operations:
  kill_switches:
    payment-provider-new:
      enabled: false
      owner: payments-oncall
      reason: incident-reference
      audit_required: true

deployment:
  artifact_digest: sha256:example
  previous_artifact_digest: sha256:previous
  config_revision: config-42
  rollback_compatible: verified
~~~

Đây là cấu trúc minh họa, không phải schema bắt buộc của một công cụ. Không nên lưu secret thật trong cấu hình này. Trường rollback_compatible phải dựa trên bằng chứng tương thích, không phải giá trị tự khai mà pipeline tin tưởng vô điều kiện.

Một pipeline hoặc control plane có thể thực hiện:

- Xác minh người yêu cầu và quyền.
- Ghi audit trước/sau thay đổi.
- Cập nhật flag hoặc deployment.
- Đợi trạng thái lan truyền.
- Kiểm tra metric và health.
- Chỉ kết thúc khi trạng thái thực tế khớp trạng thái mong muốn.

## 21. Những anti-pattern thường gặp

| Anti-pattern | Rủi ro | Cách cải thiện |
|---|---|---|
| Ẩn nút giao diện rồi coi feature đã tắt | API hoặc worker vẫn thực thi | Kiểm tra flag tại server-side boundary |
| Tắt flag nhưng không kiểm tra instance | Một số process tiếp tục chạy nhánh mới | Theo dõi flag revision trên từng instance |
| Dùng flag thay authorization | Người dùng có thể truy cập API trực tiếp | Giữ access control độc lập |
| Tắt feature và cho rằng dữ liệu đã được sửa | Side effect cũ vẫn tồn tại | Reconcile và data recovery khi cần |
| Rollback toàn service cho lỗi một feature | Tăng phạm vi tác động và downtime | Dùng flag nếu nhánh fallback an toàn |
| Tắt flag cho lỗi ở thư viện dùng chung | Code lỗi vẫn được gọi ở nhánh khác | Đánh giá dependency và rollback/fix artifact |
| Rollback code mà không kiểm tra schema | Phiên bản cũ có thể lỗi hoặc ghi sai | Kiểm tra compatibility trước rollback |
| Flag service lỗi nhưng mặc định bật | Feature rủi ro có thể tiếp tục chạy | Chọn fail-open/closed theo phân loại |
| Không dọn flag đã hết mục đích | Tăng nhánh code và khó kiểm thử | Quản lý owner, expiry và cleanup |
| Không có audit cho kill switch | Khó truy vết quyết định khẩn cấp | Ghi actor, lý do, revision và thời gian |

## 22. Checklist lựa chọn biện pháp khi có sự cố

Trước khi quyết định tắt feature hay rollback deployment, hãy xác nhận:

- [ ] Đã xác định lỗi nằm trong feature, code dùng chung, dependency hay cấu hình.
- [ ] Đã xác định mọi entry point: API, worker, queue, scheduler và integration.
- [ ] Feature flag được kiểm tra trước side effect.
- [ ] Nhánh fallback khi flag tắt đã được kiểm thử.
- [ ] Có thể xác nhận flag revision trên tất cả instance.
- [ ] Đã xem xét request và job đang chạy tại thời điểm tắt.
- [ ] Đã xác định dữ liệu và side effect đã phát sinh.
- [ ] Đã kiểm tra artifact cũ còn tồn tại và đúng digest.
- [ ] Đã xác minh code cũ tương thích schema và dữ liệu hiện tại.
- [ ] Đã đánh giá runtime config, secret và dependency liên quan.
- [ ] Có người chịu trách nhiệm và quyền thực hiện.
- [ ] Có audit cho thay đổi flag hoặc deployment.
- [ ] Đã xác minh health và business metrics sau hành động.
- [ ] Có kế hoạch phục hồi dữ liệu hoặc compensation nếu cần.
- [ ] Có điều kiện và owner để bật lại feature sau khi sửa.

## 23. Bài tập tự đánh giá

Một nền tảng thương mại điện tử vừa triển khai phiên bản V5. Release này có ba thay đổi:

- Giao diện checkout mới được bật cho 20% người dùng bằng feature flag.
- Một thư viện HTTP dùng chung được nâng cấp.
- Migration thêm cột payment_reference và bắt đầu ghi dữ liệu vào cột mới.

Sau 10 phút, nhóm vận hành quan sát thấy:

- Tỷ lệ lỗi checkout mới tăng mạnh.
- API tra cứu đơn hàng cũ vẫn hoạt động.
- Một số background worker tiếp tục gửi request qua HTTP client mới.
- Có 15 payment intent đã được tạo nhưng chưa rõ trạng thái cuối.
- Phiên bản V4 vẫn còn trong registry nhưng chỉ biết schema cũ.

Hãy xây dựng kế hoạch:

1. Có nên tắt flag checkout mới ngay không? Vì sao?
2. Tắt flag có dừng được background worker không?
3. Cần kiểm tra những side effect nào từ 15 payment intent?
4. Thư viện HTTP dùng chung có khiến rollback deployment cần thiết không?
5. V4 có thể chạy trên schema hiện tại không? Cần bằng chứng gì?
6. Có thể giữ cột payment_reference sau rollback không?
7. Khi nào cần forward fix thay vì rollback?
8. Cần xác minh trạng thái flag và artifact ở từng instance ra sao?
9. Khi nào có thể bật lại checkout mới?

Một phương án tốt có thể tắt flag để containment, dừng hoặc cấu hình lại worker, đối chiếu payment intent, kiểm tra tương thích V4 với schema đã mở rộng và quyết định rollback dựa trên phạm vi lỗi HTTP client. Sau đó cần sửa lỗi, kiểm thử cả nhánh bật/tắt và rollout lại có kiểm soát.

## Kết luận

Tắt tính năng và rollback bản triển khai là hai biện pháp có phạm vi khác nhau. Feature flag hoặc kill switch thay đổi hành vi của một khả năng trong phiên bản đang chạy; deployment rollback thay artifact hoặc revision đang phục vụ. Tắt feature phù hợp với lỗi cô lập khi nhánh fallback an toàn, còn rollback phù hợp với lỗi rộng ở code, runtime hoặc dependency.

Cả hai đều không tự hoàn tác dữ liệu và side effect đã phát sinh. Khi ứng phó sự cố, hãy ngăn tác động mới, phân loại phạm vi lỗi, kiểm tra trạng thái từng instance, đánh giá tương thích schema và artifact, rồi phục hồi dữ liệu nếu cần. Một quy trình có audit, metric và diễn tập cả đường tắt feature lẫn rollback giúp đội ngũ phản ứng nhanh mà vẫn giữ được tính nhất quán của hệ thống.

