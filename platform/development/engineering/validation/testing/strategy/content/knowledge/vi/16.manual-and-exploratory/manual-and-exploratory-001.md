# Xác định công việc cần nhận định của con người

Tự động hóa giúp kiểm tra nhanh, lặp lại và nhất quán những điều kiện có kết quả mong đợi rõ ràng. Tuy nhiên, nhiều câu hỏi về chất lượng sản phẩm cần người hiểu bối cảnh quan sát, đặt câu hỏi, diễn giải dấu hiệu và cân nhắc hậu quả. Ví dụ, một luồng có thực sự dễ hiểu với người dùng mới không, một cảnh báo bảo mật có thể khai thác trong kiến trúc hiện tại không, hay một hành vi bất thường có vi phạm quy tắc nghiệp vụ không — những câu hỏi này thường cần nhận định của con người.

Xác định công việc cần nhận định của con người là quyết định quan trọng khi xây dựng chiến lược kiểm thử. Mục tiêu không phải phân loại mọi hoạt động thành thủ công hoặc tự động một cách cứng nhắc. Nhóm cần xác định phần nào có thể được thực thi lặp lại bằng máy, phần nào cần con người khám phá hoặc đánh giá, và điểm nào cần người có thẩm quyền đưa ra quyết định. Cách phân chia phù hợp giúp sử dụng chuyên môn đúng chỗ, giữ phản hồi nhanh và tạo bằng chứng đủ tin cậy cho quyết định chất lượng.

## 1. Phân biệt thực thi thủ công và nhận định của con người

Một hoạt động được thực hiện thủ công chưa chắc cần nhiều nhận định. Ngược lại, một quy trình tự động vẫn có thể cần người diễn giải kết quả hoặc phê duyệt hành động.

Cần phân biệt ba lớp công việc:

- **Thực thi:** thao tác hoặc chạy phép kiểm tra để tạo kết quả. Việc này có thể do con người hoặc công cụ thực hiện.
- **Diễn giải:** hiểu kết quả trong ngữ cảnh, xác định ý nghĩa, mức độ tin cậy, nguyên nhân và tác động. Công việc này thường cần chuyên môn của con người.
- **Quyết định:** lựa chọn sửa, chấp nhận, điều tra thêm, giới hạn phát hành hoặc dừng triển khai. Quyết định có thể cần người sở hữu nghiệp vụ, rủi ro hoặc sản phẩm phê duyệt.

Ví dụ, người kiểm thử có thể chạy thủ công một kịch bản đăng nhập theo các bước cố định. Nếu kết quả luôn có thể xác định bằng một assertion, việc thực thi có thể tự động hóa. Nhưng khi đánh giá thông báo lỗi có giúp người dùng hiểu cách khắc phục hay không, người kiểm thử cần quan sát và nhận định. Nếu phát hiện một lỗi có thể ảnh hưởng giao dịch, người có thẩm quyền cần quyết định mức rủi ro có thể chấp nhận.

Vì vậy, hãy phân loại từng phần của công việc thay vì gắn nhãn cả hoạt động là “manual” hoặc “automated”.

## 2. Nhận diện các dấu hiệu cần con người tham gia

Một công việc thường cần nhận định của con người khi có một hoặc nhiều đặc điểm sau:

- **Kết quả mong đợi chưa thể mô tả đầy đủ bằng quy tắc:** yêu cầu dùng những từ như dễ hiểu, tự nhiên, phù hợp, hữu ích hoặc tin cậy.
- **Bối cảnh ảnh hưởng đến kết luận:** cùng một hành vi có thể đúng trong tình huống này nhưng gây hại trong tình huống khác.
- **Cần khám phá điều chưa biết:** nhóm chưa biết trước mọi đường đi, dữ liệu hoặc tương tác có thể tạo ra lỗi.
- **Có nhiều tín hiệu cần tổng hợp:** log, hành vi người dùng, dữ liệu nghiệp vụ và phản hồi từ nhiều thành phần cần được diễn giải cùng nhau.
- **Hậu quả cần phán đoán chuyên môn:** một phát hiện có thể là cảnh báo sai, rủi ro có điều kiện hoặc vấn đề nghiêm trọng tùy kiến trúc.
- **Đánh giá phụ thuộc người dùng mục tiêu:** khả năng sử dụng, khả năng tiếp cận, ngôn ngữ, nội dung và mức độ phù hợp cần được xem xét từ góc nhìn con người.
- **Cần giải quyết mâu thuẫn hoặc ngoại lệ:** tiêu chí chưa rõ, yêu cầu xung đột hoặc bằng chứng chưa đủ để kết luận tự động.
- **Quyết định có trách nhiệm và thẩm quyền:** chấp nhận rủi ro, miễn trừ, nghiệm thu hoặc phát hành cần người chịu trách nhiệm.

Các dấu hiệu này không có nghĩa phải thực hiện mọi việc bằng tay. Công cụ vẫn có thể thu thập dữ liệu, chạy kịch bản, phát hiện mẫu hoặc sắp xếp kết quả; con người tập trung vào phần cần hiểu và quyết định.

## 3. Dùng tiêu chí để quyết định mức độ tự động hóa

Có thể đánh giá công việc theo một số chiều. Không cần tạo điểm số phức tạp cho mọi nhiệm vụ; bảng câu hỏi giúp nhóm thảo luận có căn cứ.

| Chiều đánh giá | Dễ tự động hóa hơn khi | Cần nhận định của con người hơn khi |
|---|---|---|
| Kết quả mong đợi | Có điều kiện pass/fail rõ ràng | Có nhiều kết quả chấp nhận được hoặc cần diễn giải |
| Tính lặp lại | Dữ liệu và bước thực hiện ổn định | Cần thay đổi hướng theo quan sát |
| Tần suất | Chạy thường xuyên trên mỗi thay đổi | Chỉ cần thực hiện theo sự kiện hoặc theo đợt |
| Bối cảnh | Ít phụ thuộc người dùng, nghiệp vụ hoặc môi trường | Phụ thuộc vai trò, mục tiêu, hoàn cảnh hoặc hệ quả |
| Khám phá | Các trường hợp đã biết và được mô hình hóa | Cần tìm tình huống mới hoặc giả thuyết chưa biết |
| Dữ liệu đầu vào | Có thể tạo và kiểm soát bằng máy | Cần đánh giá nội dung, ngữ nghĩa hoặc dữ liệu thực tế |
| Chẩn đoán | Lỗi có dấu hiệu và nguồn rõ | Cần tổng hợp nhiều nguồn và loại trừ giả thuyết |
| Chi phí | Tự động hóa giảm đáng kể công lặp lại | Chi phí tạo và duy trì tự động hóa lớn hơn lợi ích |
| Rủi ro quyết định | Có thể xử lý theo chính sách đã định | Cần người có thẩm quyền cân nhắc hậu quả và ngoại lệ |

Một công việc có thể có điểm số tự động hóa cao ở khâu thực thi nhưng thấp ở khâu đánh giá. Ví dụ, công cụ có thể tự động quét khả năng tiếp cận và báo lỗi tương phản, nhưng chuyên gia vẫn cần xác định mức ảnh hưởng trong luồng thực tế và kiểm tra các vấn đề mà công cụ không phát hiện.

## 4. Nhận định trong kiểm thử thăm dò

Kiểm thử thăm dò (exploratory testing) là hoạt động học hỏi, thiết kế và thực thi kiểm thử diễn ra đồng thời. Người kiểm thử quan sát sản phẩm, hình thành giả thuyết, chọn thao tác tiếp theo và điều chỉnh hướng dựa trên kết quả.

Cách tiếp cận này hữu ích khi:

- Yêu cầu chưa mô tả hết hành vi.
- Tính năng mới hoặc thay đổi lớn chưa có lịch sử lỗi.
- Nhiều thành phần tương tác theo cách khó dự đoán.
- Nhóm cần tìm lỗi ngoài các trường hợp đã viết thành test case.
- Phản hồi người dùng hoặc sự cố gợi ý một tình huống chưa được mô hình hóa.

Kiểm thử thăm dò không phải thao tác ngẫu nhiên không mục tiêu. Người kiểm thử cần có mục tiêu, phạm vi, thời gian và cách ghi nhận phát hiện. Một test charter có thể mô tả:

- **Mục tiêu:** câu hỏi hoặc rủi ro muốn khám phá.
- **Phạm vi:** tính năng, vai trò, môi trường và dữ liệu.
- **Giới hạn:** điều kiện không được vượt qua hoặc thao tác có thể gây tác động.
- **Hướng khám phá:** các giả thuyết hoặc nhóm tình huống nên thử.
- **Bằng chứng:** ghi chú, log, ảnh, video, dữ liệu và bước tái hiện.
- **Kết quả:** phát hiện, câu hỏi mới và phần chưa được kiểm tra.

Ví dụ, với chức năng tải tệp, người kiểm thử có thể khám phá việc đổi tên tệp trong lúc tải, mất kết nối, gửi lại yêu cầu, tải tệp trùng, mở nhiều tab và thay đổi quyền giữa chừng. Một kịch bản cố định có thể kiểm tra một số tình huống đã biết; người kiểm thử quan sát các tương tác và phát hiện giả định chưa được xem xét.

Sau buổi khám phá, những tình huống có giá trị lặp lại nên được chuyển thành test case hoặc kiểm tra tự động phù hợp. Như vậy, nhận định của con người giúp mở rộng hiểu biết, còn tự động hóa bảo vệ những hành vi đã được xác nhận.

## 5. Đánh giá khả năng sử dụng và trải nghiệm người dùng

Khả năng sử dụng không chỉ là giao diện không có lỗi hiển thị. Cần biết người dùng mục tiêu có hiểu thông tin, tìm được hành động phù hợp, hoàn thành nhiệm vụ và phục hồi khi mắc lỗi hay không.

Con người cần tham gia khi đánh giá:

- Nội dung và nhãn điều khiển có dễ hiểu với người dùng mục tiêu không.
- Luồng thao tác có phù hợp với nhiệm vụ thực tế không.
- Thông báo lỗi có giúp người dùng hiểu điều gì xảy ra và bước tiếp theo là gì không.
- Trạng thái tải, chờ, thành công và thất bại có được truyền đạt rõ không.
- Người dùng có bị dẫn đến quyết định sai bởi cách trình bày thông tin không.
- Sản phẩm có hỗ trợ các nhu cầu, kinh nghiệm và bối cảnh sử dụng khác nhau không.

Có thể kết hợp kiểm tra tự động với đánh giá của con người. Công cụ có thể xác minh phần tử có tên truy cập, liên kết có hợp lệ hoặc trang có cấu trúc cơ bản. Người kiểm thử và người dùng đại diện cần đánh giá liệu tên đó có truyền đạt đúng mục đích, thứ tự thao tác có hợp lý và nhiệm vụ có thể hoàn thành trong bối cảnh thực tế hay không.

Khi tổ chức usability test, hãy xác định nhiệm vụ, nhóm người tham gia, môi trường, cách quan sát và tiêu chí phân tích trước. Tránh hướng dẫn người tham gia từng bước đến mức che khuất vấn đề thiết kế. Ghi lại điểm dừng, lỗi thao tác, câu hỏi, thời gian hoàn thành và nhận xét; đồng thời bảo vệ quyền riêng tư của người tham gia.

## 6. Đánh giá khả năng tiếp cận bằng cả công cụ và chuyên gia

Kiểm thử khả năng tiếp cận (accessibility testing) cần kết hợp kiểm tra tự động, kiểm tra thủ công và đánh giá với công nghệ hỗ trợ hoặc người dùng có nhu cầu phù hợp.

Công cụ tự động có thể phát hiện một số vấn đề như thiếu thuộc tính, độ tương phản theo quy tắc, cấu trúc heading hoặc liên kết không hợp lệ. Nhưng công cụ khó đánh giá đầy đủ:

- Trình đọc màn hình có truyền đạt đúng ý nghĩa và thứ tự nội dung không.
- Người dùng chỉ dùng bàn phím có tiếp cận được mọi chức năng và biết vị trí focus không.
- Lỗi biểu mẫu có được liên kết với trường và được thông báo phù hợp không.
- Nội dung, biểu tượng và hướng dẫn có dễ hiểu không.
- Luồng thao tác có thể hoàn thành với công nghệ hỗ trợ trong tình huống thực tế không.

Chuyên gia khả năng tiếp cận cần xác định tiêu chuẩn áp dụng, mức độ nghiêm trọng và phương pháp kiểm tra. Khi phù hợp, người dùng công nghệ hỗ trợ nên tham gia đánh giá để cung cấp bằng chứng từ trải nghiệm thực. Không nên xem một báo cáo quét tự động sạch là bằng chứng đầy đủ rằng sản phẩm có thể tiếp cận.

## 7. Diễn giải phát hiện và kết quả bất thường

Nhiều công cụ tạo ra cảnh báo cần được người có chuyên môn xác minh. Một cảnh báo bảo mật có thể không khai thác được trong cấu hình thực tế; một cảnh báo hiệu năng có thể do môi trường đo; một lỗi dữ liệu có thể bắt nguồn từ fixture sai thay vì sản phẩm.

Con người cần tham gia để:

1. Xác định điều kiện tạo ra cảnh báo.
2. Kiểm tra phạm vi và khả năng tái hiện.
3. Đối chiếu với kiến trúc, luồng dữ liệu và quyền thực tế.
4. Phân biệt lỗi sản phẩm, lỗi môi trường, dữ liệu kiểm thử và cảnh báo sai.
5. Đánh giá tác động và mức độ ưu tiên.
6. Đề xuất cách khắc phục hoặc giảm thiểu.
7. Xác định bằng chứng cần có để đóng phát hiện.

Ví dụ, công cụ quét dependency báo một thư viện có lỗ hổng. Người có chuyên môn cần xác định phiên bản thực tế được đóng gói, thành phần có được sử dụng trong runtime không, đường gọi có thể tiếp cận không, cấu hình có biện pháp giảm thiểu nào và nghĩa vụ cập nhật ra sao. Công cụ cung cấp tín hiệu; người đánh giá xác định ý nghĩa của tín hiệu trong hệ thống.

Với kết quả hiệu năng, chuyên gia cần phân tích workload, warm-up, cache, nhiễu, phân vị và bottleneck trước khi kết luận. Một lần chạy có độ trễ cao không đủ để kết luận hệ thống không đạt nếu môi trường hoặc phương pháp đo không phù hợp.

## 8. Đánh giá nội dung, quy tắc nghiệp vụ và ngữ cảnh

Một số lỗi không nằm ở cấu trúc dữ liệu mà ở ý nghĩa. Máy có thể xác minh phép tính theo công thức được cung cấp, nhưng người hiểu nghiệp vụ cần xác nhận công thức có đúng với chính sách và trường hợp thực tế hay không.

Công việc cần chuyên môn con người khi đánh giá:

- Nội dung thông báo, hướng dẫn và bản dịch có đúng ngữ cảnh không.
- Quy tắc nghiệp vụ có phản ánh chính sách hiện hành không.
- Một ngoại lệ có hợp lệ với loại khách hàng hoặc giao dịch cụ thể không.
- Cách trình bày dữ liệu có thể khiến người dùng hiểu sai không.
- Kết quả do hệ thống đề xuất có phù hợp với tình huống và giới hạn đã xác định không.
- Dữ liệu biên hoặc dữ liệu bất thường có ý nghĩa hợp lệ trong nghiệp vụ không.

Ví dụ, một hệ thống có thể tính đúng thuế theo công thức lập trình, nhưng công thức hoặc điều kiện áp dụng đã được diễn giải sai từ chính sách. Kiểm thử tự động sẽ xác nhận chương trình làm đúng điều đã viết; chuyên gia nghiệp vụ cần xác nhận điều đó có đúng với quy tắc cần thực hiện hay không.

Khi dùng dữ liệu thực tế, người đánh giá cần bảo vệ thông tin nhạy cảm và chỉ truy cập phần cần thiết. Mọi quyết định ngoại lệ phải được ghi nhận cùng căn cứ và thẩm quyền.

## 9. Xác định các điểm cần người phê duyệt

Một số quyết định không nên được tự động hóa hoàn toàn vì liên quan đến trách nhiệm, mức chấp nhận rủi ro hoặc cam kết với người dùng.

Ví dụ:

- Chấp nhận lỗi còn mở trước phát hành.
- Miễn trừ một quy tắc phân tích hoặc kiểm soát bảo mật.
- Xác nhận một tiêu chí nghiệm thu định tính.
- Quyết định dừng hoặc tiếp tục triển khai khi có tín hiệu bất thường.
- Chấp nhận một giới hạn tương thích hoặc khả năng tiếp cận.
- Quyết định xử lý dữ liệu hoặc sự cố có tác động đến khách hàng.
- Phê duyệt phạm vi và kết quả kiểm thử bảo mật chuyên sâu.

Công cụ có thể tổng hợp dữ liệu và đề xuất trạng thái theo quy tắc. Người có thẩm quyền vẫn cần xem xét bằng chứng, giới hạn và hậu quả trước khi quyết định. Cần phân biệt người thực hiện kiểm thử, người sở hữu rủi ro và người phê duyệt; trong một số trường hợp, các vai trò nên độc lập.

## 10. Kết hợp tự động hóa với nhận định của con người

Cách tổ chức hiệu quả thường chia hoạt động thành các phần:

- Tự động thu thập dữ liệu, chạy phép kiểm tra lặp lại và phát hiện sai lệch có quy tắc rõ.
- Con người xem xét các phát hiện có ngữ cảnh, điều tra bất thường và khám phá tình huống mới.
- Người có thẩm quyền đưa ra quyết định đối với rủi ro, ngoại lệ và nghiệm thu.
- Kết quả có giá trị được chuyển thành quy tắc, test case hoặc hướng dẫn để giảm công việc lặp lại trong tương lai.

Một luồng phối hợp có thể là:

1. Pipeline chạy test và công cụ phân tích.
2. Hệ thống gom nhóm kết quả, loại trùng và gắn phiên bản.
3. Người kiểm thử triage các phát hiện cần diễn giải.
4. Chuyên gia phù hợp xác minh các vấn đề thuộc lĩnh vực của họ.
5. Chủ sở hữu sản phẩm hoặc rủi ro quyết định khi cần chấp nhận ngoại lệ.
6. Nhóm bổ sung kiểm tra tự động cho hành vi ổn định đã được xác nhận.
7. Các trường hợp cần khám phá hoặc đánh giá định tính tiếp tục được đưa vào kế hoạch thủ công.

Sơ đồ sau thể hiện cách phân chia:

~~~mermaid
flowchart TD
    A["Yêu cầu, thay đổi hoặc tín hiệu chất lượng"] --> B["Tự động chạy kiểm tra có kết quả rõ"]
    B --> C["Tổng hợp kết quả và phát hiện bất thường"]
    C --> D{"Có cần ngữ cảnh hoặc nhận định?"}
    D -->|Không| E["Áp dụng quy tắc xử lý đã duyệt"]
    D -->|Có| F["Người kiểm thử / chuyên gia xem xét"]
    F --> G{"Cần quyết định có thẩm quyền?"}
    G -->|Có| H["Chủ sở hữu rủi ro / sản phẩm quyết định"]
    G -->|Không| I["Ghi kết luận và hành động"]
    H --> I
    E --> J["Lưu bằng chứng và cập nhật kiểm soát"]
    I --> J
    J --> K["Chuyển trường hợp lặp lại thành kiểm tra phù hợp"]
~~~

## 11. Chuẩn bị công việc cần nhận định để có kết quả nhất quán

Nhận định của con người có thể khác nhau giữa người đánh giá. Có thể cải thiện tính nhất quán bằng cách chuẩn bị tiêu chí, hướng dẫn và bằng chứng.

Một hoạt động đánh giá nên xác định:

- Mục tiêu và câu hỏi cần trả lời.
- Phạm vi, đối tượng và điều kiện.
- Tiêu chí hoặc rubric đánh giá.
- Chuyên môn và vai trò của người tham gia.
- Dữ liệu, môi trường và công cụ hỗ trợ.
- Cách ghi nhận quan sát và kết luận.
- Cách xử lý khi người đánh giá bất đồng.
- Người có quyền xác nhận hoặc phê duyệt.

Với đánh giá định tính, rubric nên mô tả các mức bằng ví dụ cụ thể. Chẳng hạn, thay vì chỉ chấm “dễ sử dụng: 4/5”, ghi nhiệm vụ nào được thực hiện, người dùng gặp trở ngại ở đâu, mức trợ giúp cần thiết và lý do đánh giá.

Với kiểm thử thăm dò, dùng charter và ghi chú phiên làm việc để người khác hiểu đã khám phá điều gì. Với triage bảo mật, dùng quy trình xác minh để các phát hiện cùng loại được đánh giá theo cách tương tự.

Khi hai chuyên gia bất đồng, ghi lại bằng chứng và giả định khác nhau, xác định người có thẩm quyền phân xử hoặc thực hiện kiểm tra bổ sung. Không nên giải quyết bất đồng chỉ bằng cách lấy trung bình các điểm số nếu bản chất tiêu chí cần một kết luận có căn cứ.

## 12. Quản lý thiên lệch và giới hạn trong nhận định

Nhận định của con người có giá trị nhưng cũng có thể chịu ảnh hưởng của thiên lệch, kinh nghiệm và điều kiện quan sát.

Một số rủi ro thường gặp:

- **Thiên lệch xác nhận:** chỉ tìm bằng chứng ủng hộ giả thuyết ban đầu.
- **Thiên lệch quen thuộc:** đánh giá luồng theo cách người phát triển đã quen dùng, không theo người dùng mới.
- **Thiên lệch gần đây:** coi lỗi mới gặp là phổ biến hơn thực tế.
- **Thiên lệch chuyên môn:** quá tập trung vào một lĩnh vực và bỏ qua tác động liên ngành.
- **Hiệu ứng người quan sát:** người tham gia thay đổi hành vi khi biết mình đang được đánh giá.
- **Mệt mỏi và áp lực thời gian:** làm giảm khả năng chú ý và bỏ sót tín hiệu.

Có thể giảm ảnh hưởng bằng cách:

- Đặt câu hỏi và giả thuyết trước khi kiểm tra.
- Dùng tiêu chí đánh giá thống nhất.
- Mời người có góc nhìn khác hoặc người dùng mục tiêu tham gia.
- Ghi lại quan sát thô trước khi đưa ra kết luận.
- Tách bằng chứng khỏi diễn giải.
- Dùng người đánh giá thứ hai với vấn đề rủi ro cao.
- Thực hiện phiên kiểm tra trong điều kiện phù hợp và có thời gian nghỉ.
- Xem xét dữ liệu lịch sử thay vì dựa vào một trải nghiệm riêng lẻ.

Không nên che giấu bất đồng hoặc mức độ không chắc chắn. Báo cáo cần thể hiện điều gì đã quan sát, điều gì được suy luận và điều gì vẫn cần xác minh.

## 13. Ghi nhận bằng chứng cho công việc có nhận định

Bằng chứng của hoạt động cần nhận định không nhất thiết là pass/fail. Nó có thể gồm quan sát, ghi chú, video, log, phản hồi người dùng, kết quả đánh giá chuyên gia hoặc biên bản quyết định.

Một hồ sơ nên ghi:

| Nội dung | Điều cần lưu |
|---|---|
| Mục tiêu | Câu hỏi hoặc rủi ro được đánh giá |
| Phạm vi | Tính năng, phiên bản, vai trò, môi trường và giới hạn |
| Người tham gia | Vai trò, chuyên môn hoặc nhóm người dùng; chỉ lưu thông tin cá nhân cần thiết |
| Phương pháp | Charter, nhiệm vụ, rubric, công cụ hoặc quy trình |
| Quan sát | Hành vi, lỗi, trở ngại và dữ liệu thực tế |
| Diễn giải | Ý nghĩa, tác động, giả định và mức độ tin cậy |
| Kết luận | Đạt, không đạt, cần điều tra hoặc chưa đủ bằng chứng |
| Hành động | Người phụ trách, thời hạn và cách xác minh |
| Phê duyệt | Người có thẩm quyền và quyết định khi cần |

Không ghi lại dữ liệu nhạy cảm của người tham gia nếu không cần thiết. Video hoặc bản ghi phiên sử dụng cần có thông báo, quyền truy cập, thời hạn lưu và cách xóa phù hợp.

Khi một phát hiện được xác nhận và có thể lặp lại, hãy chuyển nó thành test case, quy tắc kiểm tra hoặc tiêu chí chấp nhận nếu phù hợp. Giữ liên kết đến bằng chứng khám phá ban đầu để không mất bối cảnh.

## 14. Ví dụ: xác định phần việc cần nhận định trong luồng thanh toán

Giả sử một nhóm phát triển luồng thanh toán mới. Nhóm có unit test cho công thức, integration test cho API và end-to-end test cho hành trình chính. Tuy vậy, vẫn còn những câu hỏi cần con người đánh giá.

| Công việc | Phần có thể tự động | Phần cần nhận định của con người |
|---|---|---|
| Tính tổng tiền | Kiểm tra công thức, giá trị biên, đơn vị và quy tắc làm tròn đã xác định | Chuyên gia nghiệp vụ xác nhận chính sách tính phí và trường hợp ngoại lệ |
| Xử lý timeout | Mô phỏng timeout, retry, callback lặp và xác minh idempotency | Người kiểm thử đánh giá thông báo trạng thái có khiến người dùng gửi lại gây rủi ro không |
| Phân quyền hoàn tiền | Chạy kiểm tra vai trò, API và truy cập chéo tenant | Chuyên gia bảo mật đánh giá mô hình quyền và mức tác động của đường truy cập bất thường |
| Trải nghiệm thanh toán | Kiểm tra phần tử, trạng thái, điều hướng và lỗi có quy tắc | Người dùng đại diện đánh giá mức dễ hiểu, niềm tin và khả năng phục hồi khi thao tác sai |
| Phát hiện giao dịch bất thường | Cảnh báo theo ngưỡng và quy tắc đã định | Chuyên gia phân tích xác minh cảnh báo, bối cảnh giao dịch và mức độ cần điều tra |
| Quyết định phát hành | Tổng hợp kết quả test và các ngưỡng đã thống nhất | Chủ sở hữu sản phẩm và rủi ro quyết định xử lý khoảng trống hoặc ngoại lệ |

Trong phiên kiểm thử thăm dò, người kiểm thử có thể thử bắt đầu thanh toán, chuyển sang ứng dụng khác, quay lại sau khi phiên hết hạn, làm mới trang hoặc đổi phương thức thanh toán. Khi thấy thông báo “đang xử lý” nhưng không rõ giao dịch đã được gửi chưa, người kiểm thử ghi nhận vấn đề về khả năng hiểu trạng thái và đề xuất kiểm tra bổ sung.

Nhóm sau đó có thể tự động hóa xác minh trạng thái giao dịch và chống trùng lặp. Tuy nhiên, việc thông báo có dễ hiểu với người dùng hay không vẫn cần đánh giá bằng nhiệm vụ và phản hồi phù hợp. Cuối cùng, chủ sở hữu sản phẩm xem xét bằng chứng và quyết định liệu tiêu chí trải nghiệm đã được đáp ứng hay cần cải thiện.

## 15. Quy trình xác định và quản lý công việc cần nhận định

Có thể áp dụng quy trình sau khi xây dựng chiến lược:

1. **Liệt kê công việc cần kiểm tra:** bắt đầu từ yêu cầu, rủi ro, thay đổi và câu hỏi chất lượng.
2. **Xác định kết quả mong đợi:** xem kết quả có thể mô tả bằng quy tắc rõ ràng hay cần diễn giải.
3. **Phân tách thực thi, diễn giải và quyết định:** xác định phần nào tự động hóa được và phần nào cần người tham gia.
4. **Chỉ định chuyên môn:** chọn người hiểu nghiệp vụ, bảo mật, hiệu năng, khả năng tiếp cận hoặc trải nghiệm phù hợp.
5. **Chuẩn bị phương pháp:** định nghĩa charter, rubric, môi trường, dữ liệu và bằng chứng.
6. **Thực hiện và ghi nhận:** lưu quan sát, kết quả, giả định và giới hạn.
7. **Triage và quyết định:** xác minh phát hiện, phân loại rủi ro và giao hành động.
8. **Chuyển kết quả lặp lại thành kiểm tra phù hợp:** bổ sung test tự động hoặc hướng dẫn chuẩn khi hành vi đã rõ.
9. **Rà soát hiệu quả:** đánh giá chất lượng phát hiện, độ nhất quán, chi phí và khoảng trống còn lại.

## 16. Checklist xác định công việc cần nhận định của con người

Trước khi chốt cách tổ chức kiểm thử, hãy kiểm tra:

- Kết quả mong đợi có thể diễn đạt thành quy tắc pass/fail rõ ràng không?
- Công việc có phụ thuộc ngữ cảnh, ý nghĩa, trải nghiệm hoặc hậu quả nghiệp vụ không?
- Có những tình huống chưa biết cần khám phá không?
- Công cụ có thể thực thi lặp lại phần nào và tạo bằng chứng gì?
- Ai cần diễn giải cảnh báo, dữ liệu bất thường hoặc kết quả định tính?
- Có quyết định nào cần chủ sở hữu sản phẩm, rủi ro hoặc chuyên gia phê duyệt không?
- Người tham gia có đủ chuyên môn và hiểu phạm vi không?
- Phương pháp, rubric và charter có giúp kết quả nhất quán không?
- Bằng chứng có tách biệt quan sát, diễn giải và quyết định không?
- Thiên lệch, giới hạn mẫu và mức không chắc chắn đã được ghi nhận chưa?
- Phát hiện lặp lại có được chuyển thành test case hoặc kiểm soát phù hợp không?
- Quyền riêng tư và dữ liệu của người tham gia có được bảo vệ không?

Sơ đồ dưới đây tóm tắt cách quyết định phần việc cần nhận định:

~~~mermaid
flowchart TD
    A["Công việc kiểm thử hoặc tín hiệu chất lượng"] --> B["Xác định kết quả mong đợi"]
    B --> C{"Có quy tắc rõ và lặp lại được?"}
    C -->|Có| D["Tự động hóa thực thi và kiểm tra"]
    C -->|Không| E["Xác định ngữ cảnh và chuyên môn cần thiết"]
    E --> F["Con người khám phá hoặc diễn giải"]
    D --> G["Xem xét bất thường và giới hạn"]
    F --> G
    G --> H{"Cần quyết định có thẩm quyền?"}
    H -->|Có| I["Chủ sở hữu / chuyên gia quyết định"]
    H -->|Không| J["Ghi kết luận và hành động"]
    I --> J
    J --> K["Lưu bằng chứng và cải thiện kiểm tra"]
~~~

Nhận định của con người có giá trị nhất ở nơi kết quả phụ thuộc ngữ cảnh, cần khám phá điều chưa biết hoặc đòi hỏi cân nhắc hậu quả. Tự động hóa vẫn nên đảm nhiệm phần thực thi lặp lại và kiểm tra có quy tắc rõ. Khi phân tách đúng thực thi, diễn giải và quyết định, nhóm vừa giữ được tốc độ phản hồi vừa bảo đảm các kết luận quan trọng có chuyên môn, bằng chứng và trách nhiệm phù hợp.

