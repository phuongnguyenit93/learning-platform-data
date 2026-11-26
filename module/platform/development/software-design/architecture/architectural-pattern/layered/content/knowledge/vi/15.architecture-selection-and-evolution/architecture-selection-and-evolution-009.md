# Ghi quyết định ADR, cân nhắc phương án thay thế và điều kiện cần xem lại

*Chương: Lựa chọn và tiến hóa kiến trúc*

Bài học này thuộc module `SOFTWARE_DESIGN_ARCHITECTURE_ARCHITECTURAL_PATTERN_LAYERED`, có mục tiêu **Học tổ chức phần mềm theo kiến trúc phân tầng**. Trong quá trình thiết kế, nhóm thường phải chọn giữa nhiều phương án đều có thể hoạt động: tổ chức ứng dụng thành các tầng trong một tiến trình, tách module theo miền, triển khai thành nhiều dịch vụ, chọn cách lưu trữ hoặc quyết định hướng phụ thuộc. Nếu chỉ ghi lại cấu trúc cuối cùng mà không ghi lý do chọn, người bảo trì sau này khó biết quyết định xuất phát từ yêu cầu nào, phương án nào đã được cân nhắc và điều kiện nào có thể khiến lựa chọn không còn phù hợp.

**Architecture Decision Record (ADR)** là bản ghi ngắn gọn về một quyết định kiến trúc quan trọng. ADR giúp lưu lại bối cảnh, các yếu tố chi phối, phương án đã xem xét, quyết định được chọn và hệ quả dự kiến. Một ADR tốt không cố chứng minh lựa chọn là đúng mãi mãi. Nó giúp người đọc hiểu tại sao lựa chọn hợp lý trong bối cảnh tại thời điểm đó và biết khi nào cần đánh giá lại.

## 1. ADR giải quyết vấn đề gì?

Quyết định kiến trúc thường có ảnh hưởng vượt ra ngoài một lớp hoặc một chức năng. Ví dụ:

- Chọn kiến trúc phân tầng cho ứng dụng Spring Boot.
- Quyết định giữ ứng dụng dưới dạng modular monolith hay tách một số phần thành dịch vụ độc lập.
- Chọn JPA hay JDBC cho một nhóm truy vấn.
- Quy định module nghiệp vụ được phép phụ thuộc vào module nào.
- Chọn cách quản lý transaction và phát sự kiện sau commit.
- Quyết định API công khai dùng phiên bản trong URL hay cơ chế thương lượng nội dung.

Nếu quyết định chỉ nằm trong cuộc họp hoặc một đoạn chat, kiến thức dễ mất khi thành viên thay đổi. Nếu tài liệu chỉ mô tả cấu trúc hiện tại, nó không giải thích được các phương án đã bị loại bỏ và cái giá phải trả của phương án được chọn.

ADR ghi lại phần lý do đó. Nó đặc biệt hữu ích khi:

- Quyết định có ảnh hưởng đến nhiều module, nhóm hoặc hệ thống tích hợp.
- Việc đảo ngược quyết định có chi phí đáng kể.
- Có nhiều phương án với trade-off khác nhau.
- Một giả định hoặc ràng buộc quan trọng có thể thay đổi theo thời gian.
- Người mới cần hiểu vì sao codebase được tổ chức theo cách hiện tại.

Không phải mọi thay đổi code đều cần ADR. Đổi tên một biến hoặc sửa một lỗi cục bộ thường không tạo ra quyết định kiến trúc. Hãy ghi ADR khi quyết định tạo ra một ràng buộc, quy ước hoặc hệ quả dài hạn mà người khác cần hiểu và có thể cần xem xét lại.

## 2. ADR ghi lại quyết định, không chỉ ghi kết quả

Một ADR nên giúp người đọc trả lời được sáu câu hỏi:

1. **Bối cảnh:** Vấn đề nào cần giải quyết? Hệ thống đang ở trạng thái nào?
2. **Yếu tố chi phối:** Yêu cầu, ràng buộc và tiêu chí nào quan trọng nhất?
3. **Phương án:** Những lựa chọn khả thi nào đã được cân nhắc?
4. **Quyết định:** Nhóm chọn phương án nào và phạm vi áp dụng là gì?
5. **Hệ quả:** Lợi ích, chi phí, rủi ro và công việc phát sinh là gì?
6. **Điều kiện xem lại:** Bằng chứng hoặc sự kiện nào cho thấy quyết định có thể không còn phù hợp?

Một ADR chỉ viết “Chúng ta dùng kiến trúc phân tầng vì nó dễ bảo trì” chưa đủ. Cần nói rõ hệ thống đang giải quyết vấn đề gì, vì sao phân tầng phù hợp hơn các lựa chọn đã cân nhắc, và điều gì sẽ trở thành chi phí của lựa chọn đó.

ADR cũng không phải tài liệu hướng dẫn triển khai chi tiết. Nó không cần mô tả từng package hoặc từng method. Những chi tiết đó có thể nằm trong tài liệu thiết kế, sơ đồ module hoặc code. ADR tập trung vào lý do và ràng buộc của quyết định.

## 3. Cấu trúc thường dùng của một ADR

Không có một mẫu ADR bắt buộc cho mọi tổ chức. Một cấu trúc gọn có thể gồm:

| Trường | Nội dung |
|---|---|
| ID và tiêu đề | Mã định danh duy nhất và quyết định được mô tả |
| Trạng thái | Proposed, Accepted, Rejected, Deprecated hoặc Superseded tùy quy ước nhóm |
| Ngày và người chịu trách nhiệm | Thời điểm ghi nhận và người/nhóm đưa ra quyết định |
| Bối cảnh | Vấn đề, phạm vi hệ thống và lý do phải quyết định |
| Decision drivers | Tiêu chí, yêu cầu và ràng buộc quan trọng |
| Phương án đã cân nhắc | Các lựa chọn, ưu/nhược điểm và lý do loại bỏ |
| Quyết định | Phương án được chọn và phạm vi áp dụng |
| Hệ quả | Lợi ích, chi phí, rủi ro, giới hạn và biện pháp giảm thiểu |
| Điều kiện xem lại | Trigger, tín hiệu hoặc thời điểm đánh giá lại |
| Tham chiếu | Tài liệu, prototype, số liệu hoặc ADR liên quan |

Trạng thái là một quy ước của nhóm. Có thể dùng các giá trị khác, miễn là ý nghĩa rõ. Thông thường:

- **Proposed:** đang được thảo luận, chưa được chấp nhận.
- **Accepted:** đã được chấp nhận và là quyết định hiện hành.
- **Rejected:** đã xem xét nhưng không chọn.
- **Deprecated:** không còn khuyến nghị áp dụng cho quyết định mới.
- **Superseded:** đã được thay thế bởi một quyết định khác.

Một ADR được chấp nhận không nên bị viết lại âm thầm khi bối cảnh thay đổi. Giữ bản ghi cũ để hiểu lịch sử và tạo ADR mới liên kết đến ADR trước khi thay thế. Cách này bảo tồn lý do của quyết định cũ và cho thấy kiến trúc đã tiến hóa như thế nào.

## 4. Xác định bối cảnh và tiêu chí trước khi so sánh

Trước khi liệt kê phương án, hãy mô tả vấn đề bằng dữ kiện. Bối cảnh nên đủ cụ thể để người đọc biết quyết định áp dụng cho phần nào của hệ thống, ai sử dụng và giới hạn hiện tại là gì.

Ví dụ, thay vì viết:

> Ứng dụng cần một kiến trúc dễ mở rộng.

Hãy làm rõ hơn:

- Ứng dụng là hệ thống quản lý đơn hàng nội bộ, hiện do một nhóm phát triển.
- Phần lớn chức năng được phát hành cùng một ứng dụng Spring Boot.
- Các nghiệp vụ đặt hàng, thanh toán và báo cáo có một số quy tắc riêng nhưng vẫn dùng chung quy trình triển khai.
- Nhóm cần tách trách nhiệm để kiểm thử và thay đổi dễ hơn.
- Hiện chưa có yêu cầu rõ ràng về triển khai độc lập cho từng nghiệp vụ.

Tiêu chí quyết định (decision drivers) có thể bao gồm:

- **Tính đúng đắn:** có bảo vệ bất biến và ranh giới transaction cần thiết không?
- **Khả năng thay đổi:** một thay đổi nghiệp vụ có lan sang nhiều module không?
- **Khả năng kiểm thử:** quy tắc có thể kiểm tra độc lập không?
- **Hiệu năng:** số lần gọi mạng, truy vấn, bộ nhớ và độ trễ có phù hợp không?
- **Vận hành:** nhóm có thể triển khai, giám sát và khôi phục hệ thống không?
- **Tổ chức nhóm:** ai sở hữu module, ai chịu trách nhiệm trực vận hành?
- **Chi phí:** thời gian phát triển, hạ tầng và độ phức tạp dài hạn là bao nhiêu?
- **Khả năng đảo ngược:** nếu lựa chọn không phù hợp, có thể thay đổi với chi phí nào?

Không phải tiêu chí nào cũng có trọng số ngang nhau. Một hệ thống cần xử lý dữ liệu nhạy cảm có thể ưu tiên bảo mật và audit. Một dịch vụ có lưu lượng biến động lớn có thể ưu tiên khả năng mở rộng. ADR nên nêu tiêu chí quan trọng trong bối cảnh cụ thể, thay vì dùng một danh sách chung để tạo cảm giác đầy đủ.

## 5. Cân nhắc phương án thay thế công bằng

Một quyết định đáng tin cậy cần so sánh những phương án thực sự khả thi. Không nên mô tả phương án được chọn bằng toàn bộ ưu điểm và phương án bị loại bằng những nhược điểm cực đoan.

Với mỗi phương án, hãy mô tả:

- Cách nó giải quyết vấn đề.
- Những điều kiện cần có để phương án hoạt động.
- Lợi ích quan trọng.
- Chi phí và rủi ro.
- Những yêu cầu hiện tại mà nó đáp ứng hoặc chưa đáp ứng.
- Chi phí đảo ngược nếu sau này cần thay đổi.

Có thể dùng bảng để so sánh:

| Tiêu chí | Phương án A | Phương án B | Phương án C |
|---|---|---|---|
| Đáp ứng yêu cầu hiện tại | Mức độ phù hợp và bằng chứng | Mức độ phù hợp và bằng chứng | Mức độ phù hợp và bằng chứng |
| Độ phức tạp ban đầu | Công việc cần làm | Công việc cần làm | Công việc cần làm |
| Vận hành | Thành phần phải quản lý | Thành phần phải quản lý | Thành phần phải quản lý |
| Khả năng thay đổi | Những thay đổi được khoanh vùng | Những thay đổi được khoanh vùng | Những thay đổi được khoanh vùng |
| Rủi ro | Rủi ro và cách giảm thiểu | Rủi ro và cách giảm thiểu | Rủi ro và cách giảm thiểu |

Nếu dùng điểm số, cần giải thích thang điểm, trọng số và bằng chứng. Điểm số không thay thế lập luận; một bảng 4,5/5 không có tiêu chí rõ ràng có thể tạo ra độ chính xác giả. Với nhiều quyết định, mô tả định tính và nêu rõ trade-off đã đủ.

Không cần liệt kê mọi ý tưởng từng được nhắc thoáng qua. Hãy ghi các phương án có khả năng được lựa chọn và những phương án phổ biến mà người đọc có thể thắc mắc vì sao không chọn.

## 6. Ví dụ: chọn modular monolith với kiến trúc phân tầng

Giả sử một nhóm phát triển hệ thống quản lý đơn hàng bằng Java/Spring. Hệ thống có các nhóm chức năng đơn hàng, thanh toán và báo cáo. Nhóm cần ranh giới rõ giữa trình bày, điều phối ứng dụng, nghiệp vụ và truy cập dữ liệu. Hiện tại, một nhóm phát triển cùng phát hành ứng dụng; chưa có yêu cầu mỗi nhóm nghiệp vụ phải triển khai độc lập.

Ba phương án được cân nhắc:

| Phương án | Ưu điểm | Chi phí hoặc giới hạn |
|---|---|---|
| A. Modular monolith, phân tầng bên trong từng module | Gọi nội bộ đơn giản, transaction database dễ quản lý, triển khai và debug tập trung | Cần quy tắc module và dependency rõ; một tiến trình có thể cần scale cùng nhau |
| B. Microservices theo nghiệp vụ | Có thể triển khai và scale độc lập; ranh giới vận hành rõ khi ownership đã trưởng thành | Thêm giao tiếp mạng, quản lý dữ liệu phân tán, tracing, versioning và vận hành nhiều dịch vụ |
| C. Một ứng dụng monolith ít ranh giới, các chức năng gọi repository trực tiếp | Bắt đầu nhanh, ít cấu trúc | Quy tắc và truy cập dữ liệu dễ đan xen; khó khoanh vùng thay đổi khi hệ thống lớn lên |

Nhóm chọn phương án A: một modular monolith, mỗi module tổ chức trách nhiệm theo cách phù hợp và sử dụng hợp đồng rõ ràng. Ví dụ module đơn hàng có controller, application use case, mô hình nghiệp vụ và adapter lưu trữ. Module thanh toán có thể cung cấp một hợp đồng mà module đơn hàng gọi qua; không để các module truy cập tùy tiện vào bảng nội bộ của nhau.

Quyết định này không khẳng định modular monolith luôn tốt hơn microservices. Nó phù hợp với số nhóm, cách phát hành và yêu cầu hiện tại. Nếu sau này một miền cần triển khai độc lập hoặc có yêu cầu scale và cô lập lỗi riêng, nhóm có thể xem xét tách nó theo một quyết định mới.

## 7. Ví dụ ADR hoàn chỉnh

Dưới đây là một ADR minh họa. Tên hệ thống, tiêu chí và điều kiện xem lại cần được thay bằng dữ kiện của dự án thực tế.

~~~markdown
# ADR-004: Tổ chức hệ thống đơn hàng dưới dạng modular monolith phân tầng

- **Status:** Accepted
- **Date:** 2026-11-25
- **Decision owners:** Nhóm phát triển hệ thống đơn hàng

## Context

Hệ thống đơn hàng được phát triển bằng Java và Spring Boot.
Một nhóm chịu trách nhiệm phát triển và phát hành ứng dụng.
Các chức năng đơn hàng, thanh toán và báo cáo cần có ranh giới
trách nhiệm rõ, nhưng hiện chưa có yêu cầu triển khai độc lập
cho từng miền.

## Decision drivers

- Bảo vệ quy tắc nghiệp vụ và trạng thái đơn hàng.
- Kiểm thử use case và adapter độc lập.
- Giữ triển khai và vận hành phù hợp năng lực hiện tại.
- Hạn chế phụ thuộc chéo giữa các module.
- Cho phép thay đổi công nghệ lưu trữ có kiểm soát.

## Considered options

1. Modular monolith với kiến trúc phân tầng trong module.
   - Ưu điểm: lời gọi nội bộ đơn giản, transaction cục bộ,
     triển khai và quan sát tập trung.
   - Chi phí: cần kiểm soát dependency và ownership của module.

2. Microservices theo miền nghiệp vụ.
   - Ưu điểm: có thể triển khai, scale và sở hữu độc lập.
   - Chi phí: cần xử lý giao tiếp mạng, dữ liệu phân tán,
     versioning, tracing và vận hành nhiều dịch vụ.

3. Monolith không có ranh giới module rõ.
   - Ưu điểm: ít cấu trúc ban đầu.
   - Chi phí: dễ tạo phụ thuộc chéo và khó khoanh vùng thay đổi.

## Decision

Chọn modular monolith. Mỗi module tổ chức các trách nhiệm
trình bày, ứng dụng, nghiệp vụ và truy cập dữ liệu theo nhu cầu.
Các module trao đổi qua hợp đồng được công khai có chủ đích.
Module không truy cập trực tiếp bảng nội bộ của module khác.

## Consequences

- Nhóm có thể triển khai ứng dụng bằng một đơn vị vận hành.
- Transaction cục bộ và kiểm thử tích hợp đơn giản hơn so với
  quy trình trải qua nhiều dịch vụ.
- Cần kiểm tra dependency giữa module trong review.
- Một module không thể scale độc lập khỏi tiến trình chung.
- Khi có nhu cầu tách dịch vụ, cần thiết kế hợp đồng mạng,
  quyền sở hữu dữ liệu và xử lý lỗi phân tán.

## Revisit triggers

Xem xét lại quyết định khi:
- Một miền cần phát hành độc lập với nhịp phát hành chung.
- Nhu cầu scale của một miền khác biệt đáng kể và được đo lường.
- Một nhóm chuyên trách có ownership và khả năng vận hành độc lập.
- Phụ thuộc chéo giữa module gây cản trở thay đổi dù đã áp dụng
  các biện pháp kiểm soát.
- Yêu cầu cô lập lỗi hoặc bảo mật đòi hỏi ranh giới triển khai riêng.

## References

- Sơ đồ module hiện tại.
- Tài liệu yêu cầu triển khai và vận hành.
~~~

Ví dụ cho thấy ADR có thể ngắn nhưng vẫn hữu ích nếu bối cảnh, lựa chọn, hệ quả và điều kiện xem lại đủ cụ thể. Không nên sao chép ngày, mã ADR hoặc quyết định trong ví dụ vào dự án mà không xác nhận thông tin thực tế.

## 8. Viết hệ quả trung thực, bao gồm cả mặt bất lợi

Phần hệ quả thường bị viết sơ sài vì nhóm chỉ muốn ghi lợi ích của phương án đã chọn. Nhưng quyết định kiến trúc luôn có trade-off. Ghi cả mặt bất lợi giúp người bảo trì hiểu giới hạn và không lặp lại tranh luận cũ mà thiếu bối cảnh.

Có thể phân loại hệ quả:

- **Tích cực:** giảm phụ thuộc, tăng khả năng kiểm thử, giữ transaction cục bộ hoặc đơn giản hóa vận hành.
- **Tiêu cực:** thêm mapper, tăng số module, phải tuân thủ quy tắc dependency hoặc không scale từng module độc lập.
- **Rủi ro:** nhóm có thể bỏ qua ranh giới, một truy vấn dùng chung có thể tạo phụ thuộc dữ liệu, hoặc một dịch vụ ngoài có thể trở thành nút thắt.
- **Công việc tiếp theo:** tạo contract test, bổ sung giám sát, tài liệu hóa API hoặc thiết lập kiểm tra dependency.
- **Chi phí đảo ngược:** cần chuyển dữ liệu, tách deployment, thay hợp đồng hoặc cập nhật caller.

Hệ quả nên phân biệt giữa điều chắc chắn xảy ra và điều có thể xảy ra. Ví dụ, “modular monolith không thể scale độc lập từng module theo tiến trình” là hệ quả của cách triển khai đã chọn; “sau này chắc chắn phải tách microservice” là dự đoán chưa có bằng chứng.

Nếu có biện pháp giảm thiểu, hãy ghi rõ ai sẽ thực hiện hoặc nơi theo dõi. Một rủi ro được nêu nhưng không có cách quan sát hoặc xử lý sẽ khó giúp nhóm ra quyết định sau này.

## 9. Xác định điều kiện cần xem lại quyết định

Một ADR không nên kết thúc bằng câu “sẽ xem lại khi cần”. Câu đó không cho biết khi nào cần và ai nhận ra tín hiệu. Hãy định nghĩa **revisit trigger**: sự kiện, xu hướng hoặc bằng chứng đủ cụ thể để mở lại quyết định.

Có thể phân loại trigger:

| Loại trigger | Ví dụ |
|---|---|
| Nhu cầu sản phẩm | Một miền cần chu kỳ phát hành độc lập |
| Quy mô và tải | Một module có tải khác biệt rõ, đo được qua CPU, latency hoặc throughput |
| Vận hành | Sự cố ở một chức năng thường xuyên ảnh hưởng toàn ứng dụng |
| Tổ chức | Một nhóm chuyên trách có ownership và năng lực trực độc lập |
| Phụ thuộc | Thay đổi một module thường buộc sửa nhiều module khác dù hợp đồng đã rõ |
| Chi phí | Chi phí vận hành hoặc bảo trì của lựa chọn hiện tại vượt lợi ích |
| Yêu cầu bên ngoài | Quy định bảo mật, lưu trữ hoặc tích hợp mới yêu cầu ranh giới khác |

Trigger cần gắn với tín hiệu có thể quan sát. Ví dụ, thay vì “khi hiệu năng kém”, hãy ghi “khi số liệu production cho thấy module báo cáo tiêu thụ phần lớn tài nguyên và việc scale ứng dụng chung gây chi phí đáng kể, nhóm sẽ đánh giá khả năng tách workload đọc”. Không cần đặt một ngưỡng số tùy tiện nếu chưa có baseline; có thể ghi rõ nhóm sẽ xác định ngưỡng từ số liệu vận hành.

Cũng có thể đặt ngày xem lại định kỳ cho quyết định có rủi ro cao hoặc phụ thuộc vào giả định dễ thay đổi. Ngày xem lại là lời nhắc đánh giá, không phải ngày tự động hết hiệu lực. Một ADR có thể vẫn phù hợp sau khi được xem lại; khi đó ghi nhận kết quả và ngày đánh giá tiếp theo theo quy ước nhóm.

## 10. Đánh giá lại bằng bằng chứng, không theo xu hướng

Khi trigger xuất hiện, đừng mặc định rằng phải thay kiến trúc. Hãy xác minh nguyên nhân và so sánh lại các phương án trong bối cảnh mới.

Ví dụ, một endpoint chậm không tự động chứng minh cần tách microservice. Nguyên nhân có thể là N+1 query, thiếu index, tải dữ liệu dư thừa, transaction kéo dài hoặc thuật toán không phù hợp. Tối ưu truy vấn hoặc tách workload đọc có thể giải quyết vấn đề với chi phí thấp hơn.

Tương tự, một nhóm mới được thành lập không tự động có nghĩa module cần triển khai thành dịch vụ riêng. Cần xem nhóm có ownership thực sự, hợp đồng đủ ổn định, dữ liệu có thể quản lý độc lập và năng lực vận hành hay không.

Một quy trình xem lại có thể gồm:

1. Xác nhận trigger đã xảy ra và có dữ liệu hỗ trợ.
2. Kiểm tra giả định ban đầu còn đúng hay đã thay đổi.
3. Xác định vấn đề thực sự của kiến trúc hiện tại.
4. Cập nhật tiêu chí và phương án khả thi.
5. So sánh chi phí thay đổi với lợi ích kỳ vọng.
6. Chọn giữ nguyên, điều chỉnh cục bộ hoặc thay thế quyết định.
7. Ghi ADR mới nếu quyết định thay đổi; liên kết nó với ADR trước.
8. Lập kế hoạch chuyển đổi và xác minh sau khi triển khai.

Không phải mọi trigger đều dẫn đến thay đổi. Kết quả “đã xem xét, giữ nguyên vì bằng chứng chưa đủ” cũng có giá trị nếu được ghi lại.

## 11. Quản lý vòng đời ADR

ADR có giá trị khi nhóm có thể tìm, đọc và liên kết chúng với code hoặc tài liệu liên quan. Một số thực hành hữu ích:

- Lưu ADR trong repository hoặc nơi tài liệu có lịch sử phiên bản và quyền truy cập rõ.
- Dùng mã định danh và tiêu đề dễ tìm, ví dụ `0004-modular-monolith.md`.
- Mỗi ADR tập trung vào một quyết định có liên quan chặt chẽ; tránh gom nhiều quyết định độc lập vào một tài liệu dài.
- Giữ nội dung đủ ngắn để review nhưng đủ thông tin để hiểu trade-off.
- Liên kết ADR với pull request, issue, sơ đồ hoặc tài liệu triển khai có liên quan.
- Khi quyết định bị thay thế, cập nhật trạng thái ADR cũ thành Superseded theo quy ước và dẫn đến ADR mới.
- Không xóa ADR cũ chỉ vì phương án không còn được dùng; lịch sử quyết định giúp giải thích quá trình tiến hóa.

Một ADR có thể được đề xuất trong pull request, thảo luận trong buổi review kiến trúc và được chấp nhận bởi người hoặc nhóm có quyền quyết định. Tổ chức cần thống nhất ai phê duyệt quyết định có phạm vi toàn hệ thống và quyết định nào một nhóm module có thể tự đưa ra.

ADR không thay thế code review, threat modeling, kiểm thử hiệu năng hay tài liệu vận hành. Nó bổ sung phần giải thích tại sao nhóm chọn một hướng và điều kiện nào sẽ khiến hướng đó cần được xem lại.

## 12. Các lỗi thường gặp khi viết ADR

| Lỗi | Vì sao gây khó khăn | Cách cải thiện |
|---|---|---|
| Chỉ ghi phương án được chọn | Người đọc không hiểu lựa chọn khác đã được cân nhắc chưa | Ghi các phương án khả thi và lý do loại bỏ |
| Bối cảnh chung chung | Không thể đánh giá quyết định còn phù hợp không | Ghi dữ kiện, phạm vi và ràng buộc cụ thể |
| Chỉ nêu ưu điểm | Che giấu chi phí và rủi ro dài hạn | Ghi cả hệ quả tiêu cực và biện pháp giảm thiểu |
| Tiêu chí không liên quan mục tiêu | So sánh có vẻ đầy đủ nhưng không giúp chọn | Ưu tiên decision drivers thực sự chi phối |
| Điểm số không có căn cứ | Tạo cảm giác chính xác giả | Nêu trọng số, bằng chứng hoặc dùng đánh giá định tính |
| Trigger mơ hồ | Không ai biết lúc nào cần xem lại | Dùng sự kiện hoặc metric có thể quan sát |
| Sửa ADR cũ như thể quyết định chưa từng thay đổi | Mất lịch sử và lý do tiến hóa | Tạo ADR mới và đánh dấu ADR cũ bị thay thế |
| Ghi mọi thay đổi nhỏ | Tạo nhiều tài liệu khó duy trì | Chỉ ghi quyết định có ảnh hưởng kiến trúc đáng kể |

ADR quá dài cũng có thể trở thành tài liệu khó đọc. Hãy đưa chi tiết triển khai vào tài liệu phù hợp và giữ ADR tập trung vào quyết định. Ngược lại, một ADR chỉ có vài câu khẩu hiệu cũng không đủ giúp người đọc hiểu trade-off.

## 13. Checklist trước khi chấp nhận ADR

Trước khi đánh dấu ADR là Accepted, hãy kiểm tra:

- [ ] Vấn đề và phạm vi quyết định được mô tả rõ.
- [ ] Bối cảnh dựa trên dữ kiện và giả định được nêu rõ.
- [ ] Các tiêu chí quyết định phản ánh nhu cầu thật của hệ thống.
- [ ] Những phương án khả thi được mô tả công bằng.
- [ ] Lý do chọn và loại bỏ phương án có thể kiểm tra được.
- [ ] Hệ quả tích cực, tiêu cực và rủi ro được ghi nhận.
- [ ] Có biện pháp giảm thiểu hoặc công việc tiếp theo khi cần.
- [ ] Điều kiện xem lại đủ cụ thể để quan sát.
- [ ] Người hoặc nhóm có quyền quyết định đã được xác định.
- [ ] ADR liên kết đến bằng chứng và tài liệu liên quan.
- [ ] Có cách đánh dấu ADR cũ khi quyết định được thay thế.

Checklist không phải thủ tục để tạo thêm giấy tờ. Nó giúp bảo đảm quyết định quan trọng có thể được hiểu, thực hiện và đánh giá lại bởi những người không tham gia cuộc thảo luận ban đầu.

## 14. Nguyên tắc duy trì quyết định kiến trúc có thể tiến hóa

ADR ghi lại lý do của quyết định, không đóng băng kiến trúc. Một bản ghi hữu ích mô tả bối cảnh tại thời điểm lựa chọn, tiêu chí quan trọng, các phương án thực sự được cân nhắc, quyết định đã chọn, hệ quả và điều kiện cần xem lại.

Khi lựa chọn kiến trúc phân tầng, nhóm có thể bắt đầu với một ứng dụng triển khai đơn giản, nhưng cần ghi rõ ranh giới logic và trade-off. Khi quy mô, tải, cơ cấu nhóm hoặc yêu cầu vận hành thay đổi, revisit trigger cung cấp tín hiệu để đánh giá lại bằng bằng chứng. Có thể giữ quyết định cũ, điều chỉnh cách tổ chức hoặc tạo ADR mới thay thế.

Một quy trình quyết định tốt không đòi hỏi dự đoán chính xác mọi nhu cầu tương lai. Nó giúp nhóm hiểu vì sao mình đang ở vị trí hiện tại, nhận ra giả định nào đang thay đổi và chọn bước tiến hóa tiếp theo với chi phí và rủi ro được nhìn thấy rõ.

