# Xây ma trận trách nhiệm và cơ chế bàn giao rõ ràng

Hoạt động kiểm thử có sự tham gia của nhiều vai trò: chủ sở hữu sản phẩm, chuyên gia nghiệp vụ, developer, QA, kỹ sư nền tảng, vận hành, bảo mật và đôi khi cả nhà cung cấp bên ngoài. Nếu không xác định rõ ai thực hiện, ai chịu trách nhiệm cuối cùng, ai cần được tham vấn và ai có quyền quyết định, công việc dễ bị bỏ sót hoặc lặp lại. Một lỗi có thể nằm giữa nhóm phát triển và kiểm thử; môi trường có thể chưa sẵn sàng nhưng cả hai nhóm đều nghĩ nhóm kia đang xử lý; một phát hiện có thể được chuyển đi mà không có người xác nhận tiếp nhận.

Ma trận trách nhiệm và cơ chế bàn giao giúp biến sự phối hợp thành thỏa thuận có thể kiểm tra. Ma trận làm rõ quyền và nghĩa vụ theo từng hoạt động hoặc quyết định. Cơ chế bàn giao xác định điều kiện chuyển công việc, thông tin phải đi kèm, người tiếp nhận và cách xác nhận hoàn tất. Hai thành phần cần được thiết kế cùng nhau: ma trận trả lời ai sở hữu công việc, còn bàn giao bảo đảm công việc đi qua ranh giới nhóm mà không mất ngữ cảnh.

## 1. Phân biệt vai trò, trách nhiệm và quyền quyết định

Các thuật ngữ thường bị dùng lẫn nhau nhưng cần phân biệt:

- **Vai trò (role):** nhóm nhiệm vụ và quyền hạn mà một người hoặc nhóm đảm nhiệm, ví dụ QA lead, developer, product owner hoặc SRE.
- **Trách nhiệm thực hiện (responsibility):** công việc cụ thể phải được hoàn thành, chẳng hạn thiết kế test, chuẩn bị dữ liệu hoặc phân tích lỗi.
- **Trách nhiệm giải trình cuối cùng (accountability):** nghĩa vụ bảo đảm kết quả đạt yêu cầu và đưa ra quyết định trong phạm vi được giao.
- **Quyền quyết định (decision authority):** quyền phê duyệt, chấp nhận ngoại lệ, ưu tiên hoặc dừng một hoạt động.
- **Tham vấn (consultation):** cung cấp chuyên môn hoặc ý kiến trước khi quyết định.
- **Được thông báo (notification):** cần nhận thông tin để phối hợp hoặc cập nhật công việc của mình.
- **Bàn giao (handoff):** chuyển quyền xử lý hoặc quyền sở hữu một đầu việc cùng thông tin cần thiết sang cá nhân hoặc nhóm khác.

Một người có thể thực hiện công việc nhưng không có quyền chấp nhận rủi ro cuối cùng. Ví dụ, QA có thể xác minh một lỗi đã được sửa, nhưng chủ sở hữu sản phẩm hoặc người sở hữu rủi ro mới có quyền quyết định phát hành khi vẫn còn tiêu chí chưa đạt, theo chính sách tổ chức.

Cần tránh dùng cụm “cả nhóm chịu trách nhiệm” cho một đầu việc quan trọng mà không chỉ rõ người chịu trách nhiệm cuối cùng. Trách nhiệm phối hợp có thể được chia sẻ, nhưng mỗi quyết định hoặc kết quả cần có một đầu mối chịu trách nhiệm giải trình.

## 2. Khi nào cần ma trận trách nhiệm?

Ma trận đặc biệt hữu ích khi một hoạt động có nhiều nhóm tham gia, có phụ thuộc hoặc có quyết định ảnh hưởng đến chất lượng và phát hành.

Các dấu hiệu nên lập ma trận:

- Không rõ ai sở hữu yêu cầu, tiêu chí chấp nhận hoặc rủi ro.
- Test bị chậm vì chờ môi trường, dữ liệu hoặc quyền truy cập.
- Lỗi chuyển qua lại giữa QA, developer và vận hành.
- Nhiều người cùng phê duyệt một việc nhưng không ai quyết định cuối cùng.
- Các nhóm hiểu khác nhau về điều kiện “sẵn sàng kiểm thử” hoặc “đã hoàn thành”.
- Phát hiện bảo mật, hiệu năng hoặc dữ liệu cần chuyên gia riêng.
- Việc phát hành yêu cầu phối hợp nhiều bên.
- Có bàn giao giữa nhóm nội bộ, đơn vị thuê ngoài hoặc nhà cung cấp.

Với công việc nhỏ trong một nhóm, trao đổi trực tiếp có thể đủ. Không nên lập ma trận quá chi tiết cho mọi thao tác. Hãy dùng nó ở cấp hoạt động, đầu ra hoặc quyết định có rủi ro phối hợp đáng kể, sau đó liên kết đến quy trình chi tiết nếu cần.

## 3. Chọn mô hình ma trận phù hợp

Có nhiều mô hình phân định trách nhiệm. RACI là cách phổ biến, nhưng không phải lựa chọn duy nhất.

### 3.1. RACI

RACI gồm bốn loại vai trò:

- **R – Responsible:** trực tiếp thực hiện công việc. Có thể có nhiều người R nếu cần phối hợp.
- **A – Accountable:** chịu trách nhiệm cuối cùng về kết quả và bảo đảm công việc hoàn tất. Mỗi hoạt động nên có đúng một A để tránh mơ hồ.
- **C – Consulted:** được tham vấn hai chiều vì có chuyên môn hoặc bị ảnh hưởng.
- **I – Informed:** được thông báo về tiến độ hoặc kết quả; thường là giao tiếp một chiều.

RACI phù hợp khi cần xác định ai làm, ai chịu trách nhiệm cuối, ai cần góp ý và ai cần biết.

### 3.2. RASCI và mô hình mở rộng

RASCI thêm **S – Support**, dành cho người hỗ trợ thực hiện nhưng không trực tiếp sở hữu đầu ra. Một số tổ chức dùng DACI hoặc RAPID để làm rõ người dẫn dắt, người phê duyệt và người quyết định. Mô hình nào cũng cần được định nghĩa thống nhất; không nên kết hợp ký hiệu từ nhiều mô hình trong cùng ma trận mà không giải thích.

Nếu nhóm thường nhầm người hỗ trợ với người thực hiện chính, RASCI có thể hữu ích. Nếu trọng tâm là quyết định kiến trúc hoặc chấp nhận rủi ro, mô hình tập trung vào quyền quyết định có thể phù hợp hơn RACI thuần túy.

## 4. Xác định đơn vị công việc trước khi điền ma trận

Ma trận chỉ rõ nếu các hàng mô tả đầu việc hoặc quyết định có đầu ra cụ thể. Những hàng như “kiểm thử”, “chất lượng” hoặc “phát hành” quá rộng để phân công hiệu quả.

Có thể phân rã theo các hoạt động:

- Xác nhận yêu cầu và tiêu chí chấp nhận.
- Đánh giá rủi ro và chọn chiến lược kiểm thử.
- Chuẩn bị dữ liệu, môi trường và công cụ.
- Thiết kế test case, test charter và hợp đồng kiểm thử.
- Thực hiện kiểm thử chức năng và phi chức năng.
- Triage, phân loại và giao xử lý lỗi.
- Sửa lỗi và cung cấp bản dựng mới.
- Xác minh sửa lỗi và chạy hồi quy.
- Đánh giá bằng chứng và trạng thái tiêu chí.
- Chấp nhận rủi ro hoặc ngoại lệ.
- Phê duyệt phát hành và theo dõi sau triển khai.

Mỗi hàng nên có một kết quả quan sát được, ví dụ “môi trường staging được xác nhận sẵn sàng theo checklist” hoặc “phát hiện đã được phân loại và có chủ sở hữu xử lý”. Tránh phân công một nhóm cho một danh từ chung chung mà không nêu đầu ra.

## 5. Xác định vai trò và ranh giới trách nhiệm

Trước khi lập ma trận, thống nhất các vai trò tham gia và quyền của họ. Một vai trò có thể do một người hoặc một nhóm đảm nhiệm, nhưng cần có đầu mối liên hệ.

| Vai trò | Trách nhiệm thường gặp trong kiểm thử |
|---|---|
| Product owner / business owner | Xác nhận mục tiêu, quy tắc nghiệp vụ, ưu tiên và tiêu chí chấp nhận |
| QA lead / test manager | Xây dựng chiến lược, điều phối kiểm thử, theo dõi bằng chứng và rủi ro |
| QA / test engineer | Thiết kế, thực hiện, ghi nhận kết quả và tái hiện lỗi |
| Developer / service owner | Phân tích mã, sửa lỗi, cung cấp build và giải thích hành vi thành phần |
| Architect / technical lead | Rà soát thiết kế, phụ thuộc, hợp đồng và tác động kiến trúc |
| Platform / DevOps | Cấp phát môi trường, pipeline, cấu hình và quyền kỹ thuật |
| SRE / operations | Giám sát, vận hành, khả năng phục hồi, runbook và readiness vận hành |
| Security specialist | Đánh giá mối đe dọa, kiểm thử bảo mật và tư vấn xử lý phát hiện |
| Data owner / DBA | Quản lý dữ liệu, migration, backup, quyền và đối soát |
| Release manager | Điều phối lịch phát hành, điều kiện release và liên lạc giữa nhóm |
| Risk owner / approver | Chấp nhận rủi ro hoặc ngoại lệ theo thẩm quyền |

Không mặc định mọi vai trò đều phải có mặt trong mọi dự án. Chọn vai trò theo rủi ro, kiến trúc và nghĩa vụ. Nếu một người đảm nhiệm nhiều vai trò, ma trận vẫn cần làm rõ họ đang hành động với quyền nào ở từng hoạt động.

## 6. Nguyên tắc điền ma trận để tránh mơ hồ

Một ma trận RACI có ích khi tuân thủ một số nguyên tắc:

1. Mỗi hàng có một A duy nhất, trừ khi mô hình quản trị được thiết kế khác và nêu rõ cách giải quyết bất đồng.
2. Mỗi đầu việc có ít nhất một R chịu trách nhiệm thực hiện.
3. A có quyền và năng lực để bảo đảm kết quả, không chỉ mang tên trên bảng.
4. C chỉ được gán cho người có đóng góp cần thiết; quá nhiều C làm chậm quyết định.
5. I nhận thông tin đúng thời điểm, không cần tham gia mọi trao đổi.
6. Không dùng một người làm A cho quá nhiều đầu việc vượt quá năng lực thực tế.
7. Ma trận mô tả trách nhiệm, không thay thế mô tả công việc hoặc quy trình kỹ thuật.
8. Các vai trò và ký hiệu phải được giải thích ngay trong tài liệu.

Nếu một hàng có nhiều A, cần xác định lại phạm vi hoặc quyền quyết định. Ví dụ, “phê duyệt release” có thể gồm hai quyết định riêng: xác nhận readiness kỹ thuật và chấp thuận rủi ro nghiệp vụ. Tách thành hai hàng giúp chỉ định đúng người có thẩm quyền ở từng phần.

## 7. Ví dụ ma trận RACI cho hoạt động kiểm thử

Bảng dưới đây là ví dụ minh họa cho một nhóm phát triển sản phẩm có QA, Product, Development, Platform và Operations.

| Hoạt động | Product owner | QA lead | QA engineer | Developer | Platform / DevOps | Operations |
|---|---|---|---|---|---|---|
| Xác nhận tiêu chí chấp nhận | A/R | C | C | C | I | I |
| Đánh giá rủi ro và phạm vi test | C | A | R | C | C | C |
| Thiết kế test case | C | A | R | C | I | I |
| Chuẩn bị dữ liệu kiểm thử | C | A | R | C | C | I |
| Cấp phát môi trường CI/staging | I | C | C | C | A/R | C |
| Thực hiện kiểm thử | I | A | R | C | C | I |
| Phân tích lỗi ứng dụng | I | C | R | A/R | C | C |
| Sửa lỗi và tạo build mới | I | C | C | A/R | C | I |
| Xác minh sửa lỗi và hồi quy | I | A | R | C | C | I |
| Xác nhận readiness vận hành | I | C | C | C | R | A |
| Đề xuất trạng thái nghiệm thu | C | A/R | C | C | I | C |

Ma trận này cần được điều chỉnh theo cơ cấu thật. Nếu tổ chức có release manager hoặc security specialist, bổ sung họ vào các hoạt động liên quan. Nếu một chức năng có yêu cầu tuân thủ, người có thẩm quyền tuân thủ có thể cần vai trò phê duyệt riêng.

## 8. Phân biệt quyền xác nhận kỹ thuật và quyền chấp nhận rủi ro

Một nguồn xung đột phổ biến là nhầm lẫn giữa kết quả kiểm thử và quyết định kinh doanh. QA có thể xác nhận một test pass hoặc fail theo tiêu chí; điều đó không tự động trao quyền cho QA chấp nhận ngoại lệ.

Nên phân tách các quyết định:

- **Xác nhận kỹ thuật:** phép kiểm tra đã chạy đúng và bằng chứng hợp lệ.
- **Xác nhận tiêu chí:** yêu cầu hoặc acceptance criterion đã được đáp ứng.
- **Đánh giá rủi ro:** tác động và khả năng xảy ra của vấn đề còn mở.
- **Chấp nhận ngoại lệ:** người có thẩm quyền đồng ý tiếp tục với rủi ro được ghi nhận.
- **Phê duyệt release:** quyết định triển khai dựa trên các điều kiện và quyền được quy định.

Ví dụ, QA báo cáo còn một lỗi hiệu năng ở luồng ít sử dụng. QA cung cấp dữ liệu, phạm vi và tác động; chủ sở hữu sản phẩm đánh giá ảnh hưởng người dùng; SRE đánh giá khả năng giám sát và giảm thiểu; risk owner quyết định có chấp nhận ngoại lệ hay không. Quyết định cần ghi thời hạn, điều kiện theo dõi và kế hoạch khắc phục.

## 9. Thiết kế cơ chế bàn giao rõ ràng

Bàn giao không chỉ là chuyển ticket hoặc gửi tin nhắn “nhờ xử lý”. Một handoff hoàn chỉnh cần trả lời:

- Công việc hoặc quyết định nào đang được chuyển?
- Vì sao cần chuyển và kết quả mong đợi là gì?
- Người gửi đã hoàn thành những gì?
- Điều kiện đầu vào và phần còn thiếu là gì?
- Bằng chứng, dữ liệu và liên kết nào cần người nhận?
- Rủi ro, giới hạn hoặc giả định nào cần biết?
- Ai là người tiếp nhận và thời điểm cần phản hồi?
- Điều kiện nào xác định bàn giao đã được chấp nhận?

Một handoff tốt có cả thông tin và xác nhận. Người gửi không nên mặc định rằng công việc đã chuyển chỉ vì ticket đã được gán; người nhận cần xác nhận đủ thông tin và có khả năng tiếp tục.

## 10. Xác định điều kiện đầu vào và đầu ra cho từng lần bàn giao

Có thể dùng khái niệm **Entry Criteria** và **Exit Criteria** cho điểm chuyển giao.

- **Entry criteria:** điều kiện người nhận cần có để bắt đầu công việc.
- **Exit criteria:** điều kiện người gửi cần hoàn thành trước khi chuyển giao hoặc kết thúc giai đoạn.

Ví dụ, bàn giao build từ Development sang QA có thể yêu cầu:

**Điều kiện đầu vào cho QA**
- Build được gắn phiên bản và có thể triển khai.
- Phạm vi thay đổi và issue liên quan được liệt kê.
- Unit test và kiểm tra cơ bản đã có kết quả.
- Migration, cấu hình và dependency được mô tả.
- Môi trường, tài khoản và dữ liệu cần thiết sẵn sàng.
- Known issues và giới hạn đã được ghi lại.

**Điều kiện đầu ra từ Development**
- Artifact và commit có thể truy vết.
- Kết quả kiểm tra của nhóm phát triển được đính kèm.
- Hướng dẫn triển khai hoặc rollback có sẵn khi cần.
- Người chịu trách nhiệm hỗ trợ được chỉ định.

Nếu một điều kiện chưa đạt, QA có thể từ chối nhận bàn giao hoặc nhận có điều kiện với khoảng trống được ghi rõ. Không nên bắt đầu kiểm thử trong im lặng rồi sau đó tranh luận về việc thiếu đầu vào.

## 11. Bộ thông tin tối thiểu trong một handoff

Một mẫu bàn giao có thể gồm:

| Trường | Nội dung cần cung cấp |
|---|---|
| Handoff ID | Mã tham chiếu duy nhất |
| Từ / đến | Nhóm hoặc người gửi và người nhận |
| Mục đích | Công việc, quyết định hoặc đầu ra cần chuyển |
| Phạm vi | Bao gồm, loại trừ và mức ưu tiên |
| Phiên bản | Build, commit, release hoặc cấu hình liên quan |
| Trạng thái | Việc đã làm, việc còn mở và blocker |
| Điều kiện đầu vào | Những gì người nhận cần để bắt đầu |
| Bằng chứng | Test result, log, trace, ảnh, báo cáo và liên kết |
| Rủi ro / giả định | Giới hạn, known issue và điều chưa xác minh |
| Hành động tiếp theo | Việc cần làm, chủ sở hữu và thời hạn |
| Xác nhận | Người nhận, thời điểm và trạng thái chấp nhận |

Thông tin phải vừa đủ cho người nhận hành động. Không sao chép dữ liệu nhạy cảm vào ticket nếu có thể dùng liên kết đến kho bằng chứng được kiểm soát quyền. Với log, token và dữ liệu khách hàng, phải tuân thủ chính sách che dữ liệu và phân quyền.

## 12. Trạng thái bàn giao và cơ chế xác nhận

Có thể chuẩn hóa trạng thái để các bên hiểu công việc đang ở đâu:

| Trạng thái | Ý nghĩa |
|---|---|
| Draft | Người gửi đang chuẩn bị thông tin |
| Ready for Handoff | Đã đáp ứng điều kiện chuyển giao |
| Sent | Đã gửi cho người nhận |
| Acknowledged | Người nhận xác nhận đã tiếp nhận |
| Accepted | Người nhận xác nhận đủ điều kiện bắt đầu |
| Accepted with Conditions | Nhận có điều kiện và ghi rõ phần còn thiếu |
| Rejected / Returned | Chưa thể nhận; nêu lý do và thông tin cần bổ sung |
| In Progress | Người nhận đang thực hiện |
| Completed | Đầu ra đã hoàn tất và có bằng chứng |
| Closed | Người sở hữu ban đầu hoặc bên liên quan xác nhận đóng |

Không phải quy trình nào cũng cần đủ trạng thái. Điểm quan trọng là phân biệt “đã gửi” với “đã được tiếp nhận”, và “đã hoàn thành” với “đã được xác nhận”. Với việc khẩn cấp, có thể dùng kênh trao đổi nhanh nhưng vẫn phải cập nhật hồ sơ chính thức sau đó.

## 13. Bàn giao lỗi từ QA sang Development và quay lại QA

Bàn giao lỗi là một ví dụ phổ biến của phối hợp giữa nhóm.

### QA chuyển lỗi sang Development

Thông tin cần có:

- Tiêu đề ngắn mô tả hành vi sai.
- Build, môi trường, thiết bị hoặc cấu hình.
- Tiền điều kiện và dữ liệu thử.
- Các bước tái hiện rõ ràng.
- Kết quả thực tế và kết quả mong đợi.
- Tần suất tái hiện và phạm vi ảnh hưởng.
- Log, trace, ảnh hoặc video phù hợp.
- Mức độ nghiêm trọng, ưu tiên đề xuất và rủi ro.
- Test case hoặc tiêu chí liên quan.

Development xác nhận tiếp nhận, phân loại, làm rõ nếu thiếu thông tin và nêu hướng xử lý. Nếu không tái hiện được, hai bên cần cùng kiểm tra điều kiện, phiên bản và dữ liệu thay vì đóng ticket ngay.

### Development trả kết quả cho QA

Khi bàn giao bản sửa, cần nêu:

- Mã lỗi đã xử lý và nguyên nhân gốc nếu đã xác định.
- Commit, build và môi trường có bản sửa.
- Phạm vi thay đổi và thành phần có thể bị ảnh hưởng.
- Kịch bản developer đã kiểm tra.
- Migration, cấu hình hoặc dữ liệu cần cập nhật.
- Rủi ro còn lại và hướng dẫn tái kiểm tra.

QA xác minh trên đúng build, chạy test tái hiện và hồi quy theo phạm vi tác động. Nếu lỗi vẫn tồn tại, QA mở lại với bằng chứng mới. Nếu đạt, QA cập nhật trạng thái và liên kết kết quả.

## 14. Bàn giao giữa kiểm thử, vận hành và phát hành

Bàn giao sang vận hành cần cung cấp thông tin để đội vận hành hiểu hệ thống, nhận biết sự cố và khôi phục khi cần.

Một gói bàn giao có thể gồm:

- Kiến trúc triển khai và sơ đồ phụ thuộc.
- Phiên bản artifact, cấu hình và thay đổi database.
- Runbook, health check, dashboard và alert.
- Rủi ro đã biết, giới hạn và biện pháp giảm thiểu.
- Kết quả kiểm thử hiệu năng, bảo mật, phục hồi và tương thích.
- Hướng dẫn rollback, backup/restore và failover.
- Danh sách liên hệ và người trực.
- Tiêu chí readiness và điều kiện dừng rollout.
- Các ngoại lệ được phê duyệt cùng thời hạn.

Operations hoặc SRE cần xác nhận họ có quyền, công cụ, tài liệu và năng lực xử lý. Một tài liệu được gửi đi nhưng chưa được người vận hành xem xét không phải là bàn giao vận hành hoàn tất.

Release manager điều phối trạng thái và mốc thời gian; quyền chấp nhận rủi ro vẫn thuộc người được tổ chức chỉ định. Sau triển khai, cần xác định thời điểm chuyển từ hỗ trợ phát hành sang vận hành thường lệ và ai tiếp nhận cảnh báo còn mở.

## 15. Bàn giao cho chuyên gia hoặc nhà cung cấp bên ngoài

Khi kiểm thử bảo mật, khả năng tiếp cận, hiệu năng hoặc chứng nhận được thuê ngoài, phạm vi và cách bàn giao phải rõ từ đầu.

Hồ sơ cần xác định:

- Phạm vi tài sản và môi trường được phép kiểm tra.
- Mục tiêu, phương pháp và tiêu chí đầu ra.
- Thời gian, cửa sổ kiểm thử và điều kiện dừng.
- Tài khoản, quyền, dữ liệu và cách cấp/thu hồi.
- Quy tắc xử lý phát hiện nghiêm trọng.
- Cách bảo vệ bằng chứng và dữ liệu nhạy cảm.
- Định dạng báo cáo, mức chi tiết và buổi chuyển giao kết quả.
- Chủ sở hữu nội bộ chịu trách nhiệm triage và khắc phục.
- Điều kiện nghiệm thu dịch vụ và xử lý phát hiện còn mở.

Không bàn giao quyền truy cập rộng hơn phạm vi cần thiết. Trước khi đóng hợp đồng hoặc hoạt động, xác nhận tài khoản tạm đã thu hồi, dữ liệu đã được xử lý theo thỏa thuận và mọi phát hiện có chủ sở hữu nội bộ.

## 16. Quản lý bất đồng, từ chối nhận và leo thang

Một bàn giao có thể bị từ chối vì thiếu build, dữ liệu, bằng chứng hoặc quyền. Từ chối có lý do giúp ngăn việc nhận công việc chưa đủ điều kiện và làm rõ hành động cần bổ sung.

Quy trình xử lý:

1. Người nhận ghi điều kiện chưa đạt và bằng chứng.
2. Người gửi xác nhận hoặc phản hồi điểm chưa thống nhất.
3. Hai bên xác định ai có thể giải quyết blocker.
4. Nếu tranh chấp thuộc phạm vi hoặc ưu tiên, chuyển chủ sở hữu sản phẩm hoặc quản lý dự án.
5. Nếu liên quan rủi ro kỹ thuật, bảo mật hoặc vận hành, mời chuyên gia có thẩm quyền.
6. Ghi quyết định, thời hạn và điều kiện tiếp tục.
7. Cập nhật trạng thái handoff và ma trận trách nhiệm.

Không để ticket ở trạng thái “đang chờ” mà không có người theo dõi hoặc ngày cập nhật. Với blocker ảnh hưởng mốc phát hành, cần có mức leo thang và thời gian phản hồi theo quy trình của tổ chức.

## 17. Duy trì ma trận và bàn giao khi nhóm hoặc phạm vi thay đổi

Ma trận trách nhiệm dễ lỗi thời khi thay đổi nhân sự, cơ cấu, kiến trúc hoặc nhà cung cấp. Cần xem xét lại khi:

- Thêm nhóm hoặc thành phần dịch vụ mới.
- Thay đổi chủ sở hữu sản phẩm hoặc kỹ thuật.
- Chuyển hoạt động sang nhóm vận hành hoặc đối tác.
- Thay đổi quyền phê duyệt release hoặc chấp nhận rủi ro.
- Xuất hiện sự cố do công việc bị bỏ sót hoặc bàn giao không rõ.
- Quy trình CI/CD hoặc môi trường thay đổi.
- Một vai trò đang là điểm nghẽn do có quá nhiều A hoặc R.

Mỗi ma trận cần có người sở hữu, ngày cập nhật và phạm vi áp dụng. Tránh sao chép ma trận cũ sang dự án mới mà không xác minh vai trò thực tế. Khi một người rời nhóm, bàn giao trách nhiệm phải gồm các đầu việc đang mở, quyết định đã đưa ra, rủi ro, quyền truy cập và lịch tiếp theo.

## 18. Đo lường hiệu quả phối hợp và bàn giao

Có thể theo dõi một số chỉ số để nhận diện điểm nghẽn:

- Thời gian từ lúc gửi đến lúc người nhận xác nhận.
- Tỷ lệ handoff bị trả lại vì thiếu thông tin.
- Số đầu việc không có A hoặc không có R.
- Số ticket không có người sở hữu.
- Thời gian chờ giữa các nhóm.
- Số lỗi bị chuyển qua lại nhiều lần.
- Tỷ lệ bàn giao có đủ bằng chứng và phiên bản.
- Số ngoại lệ hoặc quyết định không có người phê duyệt rõ.
- Số sự cố do trách nhiệm hoặc điều kiện chuyển giao không rõ.

Không dùng các chỉ số này để thúc ép người nhận chấp nhận bàn giao khi chưa đủ điều kiện. Mục tiêu là cải thiện chất lượng thông tin, năng lực và quy trình. Cần phân tích theo loại công việc và mức độ phức tạp; một handoff bảo mật chuyên sâu có thể cần nhiều thời gian xem xét hơn một bản build thông thường.

## 19. Ví dụ: ma trận và bàn giao cho tính năng thanh toán

Một tính năng thanh toán mới cần Product xác nhận quy tắc, Development triển khai API, QA kiểm thử, Platform chuẩn bị staging, Security rà soát quyền và Operations xác nhận readiness.

Một phần ma trận trách nhiệm có thể như sau:

| Hoạt động | Product | QA lead | Developer | Platform | Security | Operations |
|---|---|---|---|---|---|---|
| Xác nhận quy tắc thanh toán | A/R | C | C | I | C | I |
| Đánh giá phạm vi kiểm thử | C | A/R | C | C | C | C |
| Triển khai API và sửa lỗi | I | C | A/R | C | C | I |
| Cấp staging và sandbox | I | C | C | A/R | C | C |
| Kiểm thử chức năng và contract | I | A | R | C | C | I |
| Đánh giá phân quyền | C | C | R | C | A/R | I |
| Xác nhận readiness vận hành | I | C | C | R | C | A |
| Chấp nhận rủi ro còn lại | A* | C | C | C | C | C |

A* trong ví dụ chỉ người có thẩm quyền theo chính sách sản phẩm/rủi ro; nếu tổ chức quy định risk owner khác Product, cần thay bằng vai trò đó. Ma trận phải có một A rõ cho từng quyết định.

### Luồng bàn giao

1. Product bàn giao tiêu chí thanh toán đã xác nhận cho Development và QA; hai nhóm xác nhận các trường hợp thành công, từ chối, timeout và hoàn tiền.
2. Development bàn giao build cho QA với commit, migration, kết quả unit test, known issues và hướng dẫn triển khai.
3. Platform xác nhận staging, sandbox, tài khoản và dữ liệu đã sẵn sàng; QA chấp nhận hoặc trả lại nếu điều kiện chưa đạt.
4. QA bàn giao phát hiện cho Development với bước tái hiện, log và mã giao dịch; Development xác nhận nhận xử lý.
5. Development trả bản sửa cùng commit và phạm vi ảnh hưởng; QA chạy retest và hồi quy.
6. QA, Security và Operations cung cấp bằng chứng readiness cho người quyết định release.
7. Operations xác nhận runbook, dashboard, alert, rollback và người trực trước khi nhận vận hành.

Nếu sandbox chưa sẵn sàng, trạng thái phải thể hiện rõ phần kiểm thử chưa thể thực hiện. Nếu có ngoại lệ phát hành, người có thẩm quyền cần phê duyệt và ghi điều kiện giám sát, thời hạn cùng hành động tiếp theo.

## 20. Quy trình xây ma trận và vận hành bàn giao

Có thể áp dụng quy trình sau:

1. **Lập danh mục hoạt động và quyết định:** phân rã theo đầu ra, rủi ro và điểm chuyển giao.
2. **Xác định vai trò:** liệt kê người thực hiện, người sở hữu, chuyên gia và bên cần nhận thông tin.
3. **Chọn mô hình:** RACI, RASCI hoặc mô hình quyết định phù hợp.
4. **Gán trách nhiệm:** xác định R, một A, C và I cho từng hàng.
5. **Rà soát quyền:** bảo đảm người A có quyền quyết định và năng lực phù hợp.
6. **Xác định handoff:** nêu người gửi, người nhận, điều kiện đầu vào/đầu ra và bằng chứng.
7. **Chuẩn hóa xác nhận:** quy định trạng thái sent, acknowledged, accepted, returned và completed.
8. **Thiết lập leo thang:** gán chủ sở hữu, thời hạn và người xử lý bất đồng.
9. **Thử trên một luồng thực tế:** kiểm tra ma trận và handoff có hoạt động trong công việc hằng ngày không.
10. **Rà soát định kỳ:** cập nhật khi thay đổi người, nhóm, kiến trúc hoặc quy trình.

~~~mermaid
flowchart TD
    A["Liệt kê hoạt động và quyết định"] --> B["Xác định vai trò và quyền"]
    B --> C["Lập ma trận RACI/RASCI"]
    C --> D["Rà soát một A và người thực hiện cho từng việc"]
    D --> E["Định nghĩa điểm bàn giao"]
    E --> F["Ghi điều kiện, bằng chứng và người nhận"]
    F --> G["Người nhận xác nhận tiếp nhận"]
    G --> H{"Đủ điều kiện?"}
    H -->|Không| I["Trả lại, ghi blocker và người xử lý"]
    I --> F
    H -->|Có| J["Thực hiện và cập nhật trạng thái"]
    J --> K["Xác nhận đầu ra và đóng bàn giao"]
    K --> L["Rà soát hiệu quả, cập nhật ma trận"]
~~~

## 21. Checklist xây ma trận trách nhiệm và cơ chế bàn giao

Trước khi áp dụng cho một dự án hoặc đợt phát hành, hãy kiểm tra:

- Hoạt động và quyết định đã được phân rã thành đầu việc có đầu ra rõ chưa?
- Các vai trò và quyền hạn đã được định nghĩa thống nhất chưa?
- Mỗi hàng có người thực hiện và đúng một người chịu trách nhiệm cuối cùng chưa?
- Người chịu trách nhiệm có đủ quyền và năng lực để quyết định không?
- Người tham vấn và người cần được thông báo có được chọn đúng mức không?
- Quyền xác nhận kỹ thuật, chấp nhận rủi ro và phê duyệt release có được phân biệt không?
- Mỗi điểm bàn giao có người gửi, người nhận và điều kiện đầu vào/đầu ra không?
- Build, phiên bản, dữ liệu, log, test result và rủi ro có được đính kèm không?
- Người nhận có cơ chế xác nhận, nhận có điều kiện hoặc trả lại không?
- Công việc bị trả lại có lý do, chủ sở hữu và thời hạn xử lý không?
- Có cơ chế leo thang cho bất đồng và blocker không?
- Quyền truy cập và dữ liệu nhạy cảm được bảo vệ trong hồ sơ bàn giao không?
- Ma trận có chủ sở hữu, phạm vi áp dụng và ngày rà soát không?
- Chỉ số phối hợp có được dùng để cải tiến quy trình thay vì ép chấp nhận bàn giao không?

Ma trận trách nhiệm chỉ có giá trị khi phản ánh quyền và năng lực thực tế. Cơ chế bàn giao chỉ hoàn chỉnh khi người nhận hiểu phạm vi, có đủ thông tin, xác nhận tiếp nhận và biết điều kiện hoàn tất. Khi hai công cụ được duy trì cùng nhau, nhóm giảm việc bỏ sót, tránh chuyển trách nhiệm không rõ ràng và giữ được tính liên tục của bằng chứng từ yêu cầu, kiểm thử, sửa lỗi đến phát hành và vận hành.

