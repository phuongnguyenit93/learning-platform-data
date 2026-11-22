# Giữ nhánh ngắn hạn và giảm độ lớn của lần tích hợp

Một thay đổi có thể bắt đầu từ một nhánh Git riêng, nhưng nếu nhánh tồn tại nhiều tuần rồi mới nhập vào nhánh chính, phần mã trên nhánh đó đã phải đi qua nhiều thay đổi khác trong thời gian chờ. Khi tích hợp, nhóm có thể gặp xung đột, lỗi tương thích, kiểm thử thất bại và nhiều giả định không còn đúng. Nếu mỗi lần nhập chứa một lượng thay đổi rất lớn, việc tìm nguyên nhân và khôi phục cũng trở nên khó khăn.

Giữ nhánh ngắn hạn và chia nhỏ lần tích hợp giúp đưa thay đổi vào luồng chung thường xuyên hơn. Mỗi lần tích hợp nhỏ có ít nội dung cần xem xét, dễ kiểm thử và dễ xác định nguyên nhân khi có lỗi. Đây là một nền tảng của CI/CD: thay đổi được tích hợp liên tục vào một nguồn mã chung, pipeline cung cấp phản hồi sớm và nhóm có thể phát hành theo mức độ sẵn sàng của sản phẩm.

## 1. Nhánh ngắn hạn và lần tích hợp nhỏ là gì?

### Nhánh ngắn hạn

**Nhánh ngắn hạn** (short-lived branch) là nhánh được tạo để thực hiện một thay đổi có phạm vi rõ ràng, sau đó được tích hợp vào nhánh đích trong thời gian ngắn. Nhánh nên tồn tại vừa đủ để hoàn thành phần việc, chạy kiểm tra cần thiết, nhận review và xử lý phản hồi.

Không có một giới hạn số ngày đúng cho mọi nhóm. Một thay đổi đơn giản có thể hoàn tất trong ngày; thay đổi phức tạp hơn có thể cần vài ngày. Điều quan trọng là nhánh không tích lũy quá nhiều khác biệt so với nhánh đích và nhóm có thể tích hợp theo từng phần có ý nghĩa.

Tuổi nhánh thường được tính từ thời điểm tạo nhánh đến thời điểm merge hoặc đóng nhánh. Có thể đo thêm thời gian từ commit đầu tiên đến lúc tích hợp, vì một nhánh được tạo sớm nhưng chưa có hoạt động trong thời gian dài vẫn có thể che khuất công việc đang dang dở.

### Lần tích hợp nhỏ

**Lần tích hợp nhỏ** (small integration batch) là một thay đổi có phạm vi đủ hẹp để reviewer hiểu được, pipeline kiểm tra được và nhóm có thể xác định tác động khi có vấn đề. Đơn vị nhỏ có thể là một phần dọc của chức năng, một bước chuẩn bị nội bộ, một thay đổi tương thích ngược hoặc một điều chỉnh độc lập.

Độ lớn không chỉ được đo bằng số dòng thêm hoặc xóa. Một pull request 40 dòng có thể rất khó hiểu nếu thay đổi nhiều khái niệm hoặc ảnh hưởng đến nhiều hệ thống. Ngược lại, một thay đổi sinh mã hoặc cập nhật dữ liệu có thể có nhiều dòng nhưng phạm vi và cách xác minh vẫn rõ ràng. Khi đánh giá, cần xem:

- Số mục đích hoặc hành vi thay đổi trong cùng một lần tích hợp.
- Số thành phần, module hoặc nhóm phụ trách bị ảnh hưởng.
- Mức độ phụ thuộc giữa các phần thay đổi.
- Khối lượng ngữ cảnh mà reviewer cần hiểu.
- Khả năng kiểm thử và xác minh độc lập.
- Khả năng tách riêng, vô hiệu hóa hoặc khôi phục thay đổi khi có lỗi.

### Tích hợp không đồng nghĩa với triển khai

Tích hợp là đưa thay đổi vào nhánh hoặc nguồn mã chung. Triển khai là đưa một phiên bản phần mềm đến một môi trường. Phát hành là làm cho năng lực hoặc thay đổi sẵn sàng với người dùng. Ba hoạt động có liên quan nhưng không bắt buộc xảy ra cùng lúc.

Một nhóm có thể merge mã thường xuyên vào main, chạy CI sau mỗi lần merge và chỉ bật chức năng mới khi đã sẵn sàng thông qua feature flag. Nhờ đó, nhóm giảm thời gian nhánh tồn tại mà vẫn kiểm soát thời điểm người dùng nhìn thấy tính năng.

## 2. Vì sao nhánh dài hạn làm tăng rủi ro tích hợp?

Trong thời gian một nhánh tồn tại, nhánh đích vẫn tiếp tục nhận commit. Càng lâu không đồng bộ, nhánh làm việc càng có nhiều khác biệt phải hợp nhất:

1. **Xung đột mã nguồn:** hai nhánh sửa cùng dòng hoặc cùng cấu trúc, buộc người phát triển giải quyết thủ công.
2. **Xung đột ngữ nghĩa:** Git có thể tự merge vì các dòng không trùng nhau, nhưng hành vi của hai thay đổi lại không tương thích.
3. **Giả định lỗi thời:** API, cấu trúc dữ liệu, cấu hình hoặc hợp đồng giữa module đã thay đổi trong khi nhánh vẫn dựa vào phiên bản cũ.
4. **Phản hồi đến muộn:** lỗi tích hợp chỉ xuất hiện khi ghép nhiều thay đổi, khiến việc xác định commit gây lỗi khó hơn.
5. **Review khó hơn:** reviewer phải hiểu nhiều quyết định và nhiều phần mã cùng lúc; các vấn đề quan trọng dễ bị bỏ sót.
6. **Khó khôi phục:** một lần merge lớn có thể chứa nhiều thay đổi độc lập, khiến revert toàn bộ gây mất công việc hợp lệ còn revert từng phần lại phức tạp.

Xung đột văn bản chỉ là phần dễ nhìn thấy. Một merge không có conflict vẫn có thể tạo lỗi runtime, sai dữ liệu hoặc vi phạm hợp đồng API. Vì vậy, giảm tuổi nhánh và tích hợp thường xuyên cần đi cùng kiểm thử tự động và khả năng tương thích giữa các phiên bản.

### Tích hợp càng lớn, phạm vi tìm lỗi càng rộng

Giả sử một pull request gồm 15 thay đổi độc lập. Nếu pipeline thất bại, nhóm phải kiểm tra nhiều khả năng và quan hệ giữa chúng. Nếu các thay đổi được tách thành những lần tích hợp nhỏ, mỗi lần có một mục đích rõ, phạm vi cần điều tra thường hẹp hơn.

Điều này không có nghĩa chia một thay đổi thành thật nhiều commit nhỏ tùy tiện. Các commit chỉ là cách tổ chức lịch sử trong nhánh. Điều quan trọng là mỗi lần merge tạo ra một trạng thái chung có ý nghĩa, có thể xây dựng và kiểm thử được.

## 3. Nguyên tắc thiết kế thay đổi để có thể tích hợp sớm

### Chia theo lát cắt dọc có giá trị

Khi triển khai một chức năng, tránh gom toàn bộ công việc giao diện, API, dữ liệu, logging và tài liệu vào một nhánh kéo dài. Hãy tìm các lát cắt dọc nhỏ đi qua những thành phần cần thiết và tạo ra một kết quả có thể xác minh.

Ví dụ, với chức năng hiển thị trạng thái đơn hàng, có thể chia công việc như sau:

| Lần tích hợp | Phạm vi | Cách xác minh |
|---|---|---|
| 1 | Thêm kiểu dữ liệu và ánh xạ trạng thái nội bộ | Unit test cho quy tắc chuyển trạng thái |
| 2 | Bổ sung endpoint đọc trạng thái, giữ tương thích API hiện tại | API test và contract test |
| 3 | Thêm giao diện hiển thị trạng thái mặc định | UI test với dữ liệu mẫu |
| 4 | Bật khả năng mới cho nhóm người dùng thử nghiệm | Kiểm tra feature flag và telemetry |

Đây là một ví dụ phân rã, không phải quy tắc rằng mọi chức năng đều cần đúng bốn lần merge. Có thể tích hợp các bước cùng lúc nếu chúng thực sự nhỏ, độc lập và dễ kiểm tra.

### Tạo trạng thái trung gian hợp lệ

Một phần chức năng chưa hoàn chỉnh vẫn có thể được tích hợp nếu trạng thái trung gian không phá vỡ khả năng build, kiểm thử hoặc vận hành của nhánh chính. Có thể dùng:

- **Feature flag:** mã đã được tích hợp nhưng hành vi mới mặc định tắt.
- **API tương thích ngược:** bổ sung trường hoặc endpoint mới mà client cũ vẫn hoạt động.
- **Triển khai theo giai đoạn:** đưa mã đến môi trường thử nghiệm hoặc một nhóm người dùng trước.
- **Adapter hoặc lớp chuyển tiếp:** cho phép mã cũ và mã mới cùng tồn tại trong giai đoạn chuyển đổi.
- **Thay đổi dữ liệu theo kiểu mở rộng rồi thu hẹp:** thêm cấu trúc mới, chuyển đổi dần, sau đó mới xóa cấu trúc cũ khi không còn bên sử dụng.

Không nên dùng feature flag để che giấu một nhánh lớn chưa được tích hợp. Mục tiêu là tích hợp mã theo từng phần an toàn, có kiểm soát; cờ tính năng chỉ quản lý thời điểm hành vi được bật.

### Giữ hợp đồng tương thích trong quá trình chuyển đổi

Khi nhiều phiên bản ứng dụng có thể chạy đồng thời, một thay đổi cần xem xét khả năng tương thích giữa mã mới, mã cũ, dữ liệu và client. Ví dụ, nếu đổi tên một trường API ngay lập tức, client cũ có thể lỗi dù mã backend mới đã build thành công.

Một trình tự chuyển đổi an toàn thường là:

1. Bổ sung trường hoặc endpoint mới trong khi vẫn hỗ trợ dạng cũ.
2. Triển khai backend có thể đọc hoặc ghi theo cả hai dạng khi cần.
3. Chuyển client hoặc dữ liệu sang dạng mới theo từng đợt.
4. Quan sát telemetry để xác nhận không còn bên sử dụng dạng cũ.
5. Xóa hỗ trợ cũ trong một lần tích hợp riêng sau khi đã xác minh.

Với cơ sở dữ liệu, ưu tiên thay đổi có tính bổ sung trước khi xóa hoặc đổi cấu trúc đang được phiên bản cũ sử dụng. Không nên gộp thay đổi phá vỡ tương thích vào một lần merge lớn mà không có kế hoạch chuyển đổi.

## 4. Quy trình làm việc với nhánh ngắn hạn

Một quy trình đơn giản có thể bắt đầu từ main và dùng pull request để review:

**Bước 1: Cập nhật nhánh đích.** Bắt đầu từ trạng thái mới nhất của nhánh tích hợp chung để giảm khác biệt ngay từ đầu.

~~~bash
git switch main
git pull --ff-only origin main
~~~

**Bước 2: Tạo nhánh theo một mục tiêu rõ ràng.**

~~~bash
git switch -c feat/order-status-endpoint
~~~

Tên nhánh nên gợi được loại thay đổi và phạm vi. Tránh dùng một nhánh chung cho nhiều công việc không liên quan.

**Bước 3: Thực hiện thay đổi theo từng bước nhỏ.** Commit khi một phần công việc có ý nghĩa và có thể giải thích. Chạy kiểm tra phù hợp trong quá trình phát triển, thay vì đợi đến cuối mới chạy toàn bộ.

~~~bash
git add src/
git commit -m "feat: add order status endpoint"
~~~

**Bước 4: Mở pull request sớm.** Khi đã có phần thay đổi đủ để reviewer hiểu hướng triển khai, có thể mở pull request ở trạng thái draft. Điều này giúp nhận phản hồi sớm về thiết kế và phạm vi. Pull request chỉ nên chuyển sang trạng thái sẵn sàng merge khi mô tả, kiểm tra và các điều kiện chất lượng đã đáp ứng.

**Bước 5: Đồng bộ với nhánh đích.** Nếu nhánh đích đã tiến lên trong lúc làm việc, cập nhật nhánh theo quy ước của nhóm:

~~~bash
git fetch origin
git rebase origin/main
~~~

Rebase phù hợp với nhánh cá nhân chưa được người khác dựa vào. Với nhánh dùng chung, nhóm có thể chọn merge nhánh đích để tránh viết lại lịch sử mà người khác đang sử dụng. Không nên force-push một nhánh chung nếu chưa thống nhất với các cộng tác viên.

**Bước 6: Chạy kiểm tra trên trạng thái sẽ được merge.** Pipeline cần xác nhận build, test và các cổng chất lượng bắt buộc trên đúng tổ hợp commit. Nếu có merge queue, hệ thống nên kiểm tra thay đổi với trạng thái nhánh đích mới nhất trước khi đưa vào nhánh chung.

**Bước 7: Merge và xóa nhánh.** Sau khi review và CI đạt yêu cầu, tích hợp thay đổi. Xóa nhánh đã hoàn tất để danh sách nhánh phản ánh công việc đang thực sự diễn ra.

~~~bash
git switch main
git pull --ff-only origin main
git branch -d feat/order-status-endpoint
~~~

Lệnh xóa nhánh cục bộ chỉ là bước dọn dẹp; thao tác xóa nhánh từ xa phụ thuộc nền tảng Git hosting hoặc quy trình của nhóm.

## 5. Thiết kế pull request nhỏ và dễ review

Pull request là một điểm kiểm soát quan trọng của luồng tích hợp. Một pull request tốt giúp reviewer hiểu được mục đích, đánh giá rủi ro và xác minh hành vi thay đổi.

### Giới hạn phạm vi bằng mục tiêu

Trước khi mở pull request, hãy có thể trả lời ngắn gọn:

- Vấn đề hoặc hành vi nào đang được thay đổi?
- Phần nào nằm trong phạm vi và phần nào được để lại cho lần sau?
- Vì sao cách triển khai này tương thích với hệ thống hiện tại?
- Kiểm tra nào chứng minh thay đổi hoạt động?
- Nếu có sự cố, có thể tắt, revert hoặc khôi phục ra sao?

Nếu mô tả cần nhiều mục tiêu độc lập, có thể đó là dấu hiệu nên tách pull request. Tuy nhiên, đừng tách đến mức reviewer phải ghép nhiều phần rời rạc mới hiểu được một thay đổi.

### Dùng kích thước như tín hiệu, không phải luật cứng

Số dòng thay đổi, số file và thời gian review có thể giúp phát hiện pull request quá lớn. Không nên đặt một ngưỡng LOC duy nhất cho mọi loại thay đổi. Một cập nhật sinh mã, đổi định dạng hoặc cập nhật dependency có đặc điểm review khác với thay đổi thuật toán hoặc hợp đồng API.

Có thể dùng các tín hiệu sau để yêu cầu chia nhỏ hoặc bổ sung giải thích:

| Tín hiệu | Vì sao cần chú ý |
|---|---|
| Nhiều mục tiêu không liên quan | Khó review và khó revert từng phần |
| Chạm nhiều module không có quan hệ rõ | Phạm vi ảnh hưởng và trách nhiệm review tăng |
| Thay đổi API và client cùng lúc theo cách phá vỡ tương thích | Khó triển khai theo thứ tự an toàn |
| Không có test hoặc bằng chứng xác minh | Reviewer phải tự suy luận hành vi |
| PR tồn tại lâu, liên tục phát sinh thêm phạm vi | Khả năng tích lũy thay đổi và xung đột tăng |
| Review bị chia thành nhiều vòng lớn | Có thể phạm vi hoặc thiết kế ban đầu chưa đủ rõ |

### Viết mô tả và bằng chứng có thể kiểm tra

Một mô tả pull request nên nêu mục tiêu, cách triển khai, cách kiểm tra, ảnh hưởng vận hành và ghi chú triển khai nếu có. Với thay đổi giao diện, thêm ảnh hoặc video ngắn. Với API, cung cấp ví dụ request/response. Với thay đổi dữ liệu, mô tả khả năng tương thích và thứ tự triển khai.

Reviewer cần tập trung vào tính đúng đắn, khả năng bảo trì, bảo mật, tương thích và mức độ kiểm thử. Một PR nhỏ không tự động có chất lượng cao; nó vẫn cần review và các cổng CI phù hợp.

## 6. Giữ nhánh chính luôn tích hợp được

Nhánh chính chỉ có thể nhận thay đổi thường xuyên nếu trạng thái của nó luôn đủ tin cậy để các thành viên khác tiếp tục làm việc. Nhóm cần định nghĩa những điều kiện tối thiểu trước khi merge.

### Cổng kiểm tra trước khi tích hợp

Tùy hệ thống, pipeline có thể gồm:

1. Kiểm tra định dạng và quy tắc mã nguồn.
2. Build để phát hiện lỗi biên dịch hoặc đóng gói.
3. Unit test cho logic thay đổi.
4. Integration test hoặc contract test cho các ranh giới bị ảnh hưởng.
5. Quét bảo mật và kiểm tra dependency theo chính sách.
6. Kiểm tra trạng thái nhánh đích và điều kiện review.

Không phải mọi PR đều cần chạy toàn bộ bộ kiểm thử chậm. Có thể chạy kiểm tra nhanh cho mỗi commit, kiểm tra rộng hơn trước merge hoặc chạy theo phạm vi ảnh hưởng. Dù vậy, phải bảo đảm kiểm tra bắt buộc đủ để nhánh chính duy trì trạng thái có thể build và phát hành theo chính sách.

### Tích hợp tuần tự khi nhiều PR cùng chờ

Khi nhiều pull request cùng vượt qua CI dựa trên một commit cũ của main, việc merge PR thứ nhất có thể làm thay đổi trạng thái đích khiến PR tiếp theo không còn được xác minh trên tổ hợp mới nhất. **Merge queue** hoặc cơ chế tuần tự hóa tương đương có thể xếp các thay đổi, kiểm tra chúng trên trạng thái dự kiến sau các lần merge trước và chỉ đưa vào nhánh chính khi điều kiện vẫn đạt.

Merge queue giúp giảm lỗi do nhiều PR cùng cạnh tranh cập nhật nhánh chính. Nó không thay thế review, test hoặc việc giữ thay đổi nhỏ.

### Phản hồi nhanh và sửa lỗi ngay

Nếu một lần merge làm CI của nhánh chính thất bại, nhóm nên ưu tiên khôi phục trạng thái xanh. Tùy nguyên nhân, có thể sửa ngay, revert thay đổi gây lỗi hoặc tắt hành vi bằng feature flag. Không nên để nhiều commit tiếp tục chồng lên một nhánh chính đang hỏng vì điều đó làm tăng số người bị chặn và khiến việc tìm nguyên nhân khó hơn.

## 7. Các kỹ thuật hỗ trợ tích hợp thường xuyên

### Feature flag

Feature flag cho phép tích hợp mã chưa sẵn sàng bật rộng rãi. Cờ cần có giá trị mặc định an toàn, quyền thay đổi rõ ràng và khả năng quan sát. Nên ghi nhận chủ sở hữu và thời điểm dự kiến xóa cờ để tránh tích lũy nhiều nhánh logic lâu dài.

~~~java
if (featureFlags.isEnabled("order-status-v2", customerId)) {
    return orderStatusV2Service.getStatus(orderId);
}
return orderStatusV1Service.getStatus(orderId);
~~~

Đoạn mã minh họa cách chọn hành vi theo cờ. Trong hệ thống thực tế, cần cân nhắc cách nạp cấu hình, xử lý khi dịch vụ flag không khả dụng, kiểm soát quyền bật cờ và kiểm thử cả hai nhánh hành vi.

### Branch by abstraction

Khi cần thay thế một thành phần lớn, tạo một abstraction ổn định để mã hiện tại và triển khai mới có thể cùng tồn tại. Sau đó chuyển dần người gọi sang implementation mới và xóa implementation cũ trong một thay đổi riêng. Cách này giảm nhu cầu giữ một nhánh thay thế kéo dài.

### Pairing hoặc mob programming

Với thay đổi khó chia nhỏ, hai hoặc nhiều người có thể cùng làm trên một nhánh ngắn hoặc cùng một phiên làm việc. Việc tích hợp liên tục trong lúc phát triển giúp giải quyết khác biệt sớm và chia sẻ hiểu biết. Cách làm này hữu ích khi phần việc có nhiều phụ thuộc hoặc cần phối hợp thiết kế.

### Tự động hóa phần lặp lại

Script kiểm tra cục bộ, template pull request, rule bảo vệ nhánh, CI bắt buộc và merge queue giúp giảm thao tác thủ công. Tự động hóa nên đưa phản hồi rõ ràng và có thể hành động; một check thất bại chỉ ghi "failed" mà không có log hoặc liên kết bằng chứng sẽ làm tăng thời gian xử lý.

## 8. Đo lường tuổi nhánh và kích thước lần tích hợp

Không thể cải thiện điều chưa quan sát được. Nhóm có thể bắt đầu với một số chỉ số đơn giản:

| Chỉ số | Cách hiểu | Câu hỏi quản lý |
|---|---|---|
| Branch age | Thời gian từ lúc tạo nhánh đến merge hoặc đóng | Nhánh có tồn tại quá lâu không? |
| Time to first review | Thời gian từ lúc PR sẵn sàng review đến phản hồi đầu tiên | PR đang chờ người tiếp nhận hay chờ xử lý? |
| Time to merge | Thời gian từ lúc PR sẵn sàng đến lúc merge | Quy trình review và tích hợp có bị tắc? |
| PR size | Số file, dòng thay đổi, mục tiêu và thành phần bị ảnh hưởng | Lần tích hợp có quá khó hiểu hoặc quá rộng? |
| Integration frequency | Số lần tích hợp vào nhánh chung trong một khoảng thời gian | Nhóm có tích hợp đều đặn không? |
| Conflict/rework rate | Tần suất conflict, sửa lại hoặc lỗi do tích hợp | Khác biệt tích lũy có đang gây chi phí? |
| Mainline health | Tỷ lệ pipeline nhánh chính thành công và thời gian nhánh chính bị hỏng | Nhánh chung có đủ tin cậy để tiếp tục làm việc? |

Nên theo dõi phân phối như trung vị và p85/p95, thay vì chỉ nhìn trung bình. Một vài nhánh kéo dài nhiều tuần có thể bị che bởi nhiều nhánh hoàn tất trong ngày.

Không nên dùng số lần commit hoặc số pull request làm thước đo năng suất cá nhân. Nếu biến chỉ số thành mục tiêu cứng, nhóm có thể tạo nhiều PR vụn vặt, chia commit thiếu ý nghĩa hoặc merge thay đổi chưa đủ kiểm tra. Chỉ số là tín hiệu để tìm điểm nghẽn của hệ thống làm việc.

### Ví dụ đọc số liệu

Giả sử trong một tháng, nhóm có:

- Tuổi nhánh trung vị giảm từ 6 ngày xuống 2 ngày.
- Thời gian chờ review p85 vẫn ở mức 3 ngày.
- Kích thước PR trung vị giảm, nhưng tỷ lệ CI thất bại sau merge tăng.

Có thể kết luận nhóm đã rút ngắn thời gian tồn tại của nhánh, nhưng chưa thể kết luận toàn bộ luồng tích hợp tốt hơn. Cần điều tra vì sao review vẫn chậm và vì sao lỗi sau merge tăng. Có thể PR nhỏ hơn nhưng thiếu kiểm thử, hoặc merge queue chưa xác minh đúng trạng thái đích. Đánh giá cải tiến phải xem đồng thời tốc độ, chất lượng và độ ổn định của nhánh chính.

## 9. Những tình huống khó và cách xử lý

### Một chức năng cần nhiều tuần mới hoàn chỉnh

Chia công việc thành các bước có thể tích hợp và giữ hành vi mới tắt bằng feature flag. Tập trung vào việc tạo trạng thái trung gian hợp lệ. Nếu không thể bật tính năng cho người dùng, mã vẫn có thể được tích hợp khi phần chưa hoàn chỉnh được cô lập và không làm hỏng luồng hiện tại.

### Thay đổi xuyên nhiều module

Tìm ranh giới hợp đồng giữa các module. Có thể bổ sung API hoặc adapter tương thích trước, sau đó chuyển từng bên sử dụng. Nếu các module phải thay đổi đồng thời, dùng một kế hoạch tích hợp có thứ tự và kiểm thử hợp đồng để giảm phụ thuộc vào thao tác thủ công.

### Nhánh có nhiều người cùng làm

Thống nhất quy ước commit và đồng bộ. Tránh rebase hoặc force-push tùy tiện trên nhánh mà người khác đang dựa vào. Nếu công việc đã đủ lớn để nhiều người phát triển độc lập, cân nhắc tách thành nhánh ngắn riêng và tích hợp qua pull request nhỏ.

### Xung đột liên tục trên cùng một file

Đây có thể là dấu hiệu nhiều nhóm đang sửa cùng một vùng trách nhiệm hoặc kiến trúc có điểm tập trung thay đổi. Trao đổi sớm về quyền sở hữu, chia module, API hoặc lịch thay đổi. Chỉ tăng tần suất merge mà không giải quyết phụ thuộc tổ chức sẽ không loại bỏ nguyên nhân.

### PR nhỏ nhưng hàng đợi review dài

Chia nhỏ PR làm giảm thời gian đọc mỗi thay đổi nhưng không tự tạo thêm năng lực review. Làm rõ reviewer theo module, giới hạn WIP, phân công người dự phòng và cung cấp bằng chứng ngay trong PR. Có thể review thiết kế sớm khi PR còn draft để tránh chờ đến lúc hoàn thiện mới phát hiện hướng đi không phù hợp.

### Cần duy trì nhánh phát hành

Nhánh phát hành có thể tồn tại lâu hơn nhánh tính năng vì mục tiêu là ổn định một phiên bản đã chọn, áp dụng sửa lỗi được kiểm soát và tạo bản phát hành. Đây là loại nhánh có mục đích riêng. Nhóm cần quy định cách đưa bản sửa từ nhánh phát hành trở lại nhánh chính để tránh phân kỳ lâu dài. Không nên dùng nhánh phát hành làm nơi phát triển tính năng mới.

## 10. Lộ trình áp dụng trong nhóm

Có thể bắt đầu từ một số thay đổi nhỏ trong cách làm việc:

1. **Thống nhất nhánh tích hợp chung.** Xác định nhánh nào phải luôn build được và các điều kiện bảo vệ nhánh.
2. **Đặt mục tiêu cho từng nhánh.** Mỗi nhánh chỉ phục vụ một thay đổi hoặc một phần việc có quan hệ chặt chẽ.
3. **Mở PR sớm.** Dùng draft để nhận phản hồi về thiết kế và phạm vi khi công việc chưa hoàn tất.
4. **Giới hạn công việc đang làm (WIP).** Hoàn tất và tích hợp công việc đang dở trước khi mở thêm nhiều nhánh mới.
5. **Tách thay đổi lớn.** Chia theo lát cắt dọc, hợp đồng tương thích hoặc các bước triển khai an toàn.
6. **Tự động hóa kiểm tra.** Bảo đảm build và test cung cấp phản hồi đủ nhanh trước khi merge.
7. **Theo dõi điểm nghẽn.** Đo tuổi nhánh, thời gian review, kích thước PR, tần suất tích hợp và sức khỏe nhánh chính.
8. **Cải tiến theo dữ liệu.** Nếu chờ review là vấn đề, cải thiện phân công và WIP; nếu conflict tăng, xem lại tần suất đồng bộ và ranh giới module; nếu lỗi sau merge tăng, xem lại kiểm thử và điều kiện merge.

Không cần chuyển toàn bộ quy trình sang trunk-based development trong một lần. Có thể bắt đầu bằng cách rút ngắn nhánh tính năng, giảm phạm vi PR và tích hợp thường xuyên hơn. Khi nhánh chính đã có kiểm tra tự động đáng tin cậy, nhóm có thể tiến dần đến mô hình tích hợp liên tục hơn.

## 11. Checklist trước khi merge

- [ ] Nhánh phục vụ một mục tiêu rõ ràng và chưa tích lũy phạm vi ngoài kế hoạch.
- [ ] Mô tả PR giải thích vấn đề, giải pháp, tác động và cách kiểm tra.
- [ ] Thay đổi có kích thước phù hợp để reviewer hiểu được; phần lớn không liên quan đã được tách.
- [ ] Nhánh đã được đồng bộ với nhánh đích theo quy ước của nhóm.
- [ ] Build, test và các cổng chất lượng bắt buộc đều đạt trên trạng thái sẽ merge.
- [ ] API, dữ liệu và cấu hình vẫn tương thích với các phiên bản có thể cùng tồn tại.
- [ ] Chức năng chưa sẵn sàng được cô lập bằng cơ chế phù hợp, chẳng hạn feature flag có chủ sở hữu.
- [ ] Có cách quan sát, tắt hoặc khôi phục thay đổi khi xảy ra sự cố.
- [ ] Sau khi merge, nhánh được dọn dẹp và trạng thái nhánh chính được theo dõi.

Giữ nhánh ngắn hạn và giảm độ lớn của lần tích hợp là cách giảm lượng khác biệt phải xử lý cùng một lúc. Khi thay đổi được chia thành phần nhỏ có thể xác minh, nhánh chính nhận phản hồi thường xuyên hơn, review tập trung hơn và lỗi dễ truy tìm hơn. Kết hợp với kiểm thử tự động, hợp đồng tương thích và khả năng kiểm soát hành vi bằng feature flag, nhóm có thể tích hợp liên tục mà vẫn duy trì chất lượng và khả năng phát hành an toàn.
