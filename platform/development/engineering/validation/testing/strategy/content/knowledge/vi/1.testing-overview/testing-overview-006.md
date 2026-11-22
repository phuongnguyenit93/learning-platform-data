# Chiến lược ở cấp tổ chức, sản phẩm, dự án và từng phạm vi kiểm thử

Một chiến lược kiểm thử hiệu quả phải trả lời được hai câu hỏi: **chúng ta cần bảo vệ chất lượng nào và sẽ dùng cách nào để thu thập đủ bằng chứng trước khi đưa thay đổi đến người dùng?** Câu trả lời không thể chỉ nằm trong một danh sách test case. Nó cần được xác định ở nhiều cấp, từ định hướng chung của tổ chức đến quyết định kiểm thử một chức năng cụ thể.

Bốn cấp thường gặp là tổ chức, sản phẩm, dự án và phạm vi kiểm thử. Chúng liên kết với nhau nhưng có mục tiêu và mức độ chi tiết khác nhau. Chiến lược cấp cao tạo ra nguyên tắc và giới hạn; các cấp thấp hơn chuyển chúng thành lựa chọn phù hợp với rủi ro, kiến trúc, tiến độ và thay đổi đang thực hiện. Kết quả kiểm thử, sự cố sau phát hành và phản hồi vận hành lại cung cấp dữ liệu để điều chỉnh chiến lược ở cấp cao hơn.

## 1. Chiến lược kiểm thử là gì?

Chiến lược kiểm thử mô tả **cách tiếp cận có chủ đích để đánh giá chất lượng và giảm rủi ro**. Nó làm rõ:

- Mục tiêu chất lượng và rủi ro cần kiểm soát.
- Những phần cần kiểm thử, mức độ kiểm thử và thứ tự ưu tiên.
- Các kỹ thuật, loại kiểm thử, môi trường, dữ liệu và công cụ sẽ sử dụng.
- Trách nhiệm của các vai trò tham gia.
- Bằng chứng cần có để đánh giá kết quả và đưa ra quyết định phát hành.

Chiến lược khác với kế hoạch kiểm thử. Chiến lược nêu cách tiếp cận và lý do lựa chọn; kế hoạch chuyển cách tiếp cận đó thành công việc cụ thể, người phụ trách, lịch thực hiện, nguồn lực và mốc kiểm soát. Thiết kế kiểm thử đi sâu hơn nữa vào điều kiện, dữ liệu, bước thực hiện và kết quả mong đợi của từng trường hợp.

Kiểm thử không thể chứng minh tuyệt đối rằng phần mềm không còn lỗi. Mục tiêu thực tế là tạo ra bằng chứng đủ tin cậy để hiểu chất lượng hiện tại, phát hiện vấn đề sớm và quyết định phần rủi ro còn lại có thể chấp nhận hay không.

## 2. Bốn cấp của chiến lược kiểm thử

### 2.1. Cấp tổ chức: thiết lập nguyên tắc và năng lực chung

Chiến lược cấp tổ chức định hướng cách các nhóm trong tổ chức tiếp cận chất lượng. Cấp này phù hợp để thống nhất những điều cần áp dụng rộng rãi, tránh việc mỗi nhóm tự đặt tiêu chuẩn không tương thích.

Các quyết định chính thường gồm:

- **Nguyên tắc chất lượng:** chất lượng là trách nhiệm của cả nhóm phát triển và vận hành; kiểm thử bắt đầu từ lúc làm rõ yêu cầu; ưu tiên ngăn ngừa lỗi và phản hồi nhanh.
- **Khẩu vị rủi ro và chuẩn phát hành:** xác định loại rủi ro nào không được phép tồn tại khi phát hành, cách xử lý lỗi nghiêm trọng và ai có quyền chấp nhận rủi ro còn lại.
- **Chuẩn và quy trình dùng chung:** quy ước về review, kiểm thử mã nguồn, kiểm thử bảo mật, quản lý lỗi, truy vết yêu cầu và lưu bằng chứng.
- **Nền tảng và công cụ:** CI/CD, môi trường kiểm thử, quản lý dữ liệu kiểm thử, báo cáo kết quả và khả năng quan sát hệ thống.
- **Năng lực và trách nhiệm:** kỹ năng cần có, cách phối hợp giữa phát triển, kiểm thử, bảo mật, vận hành và chủ sở hữu sản phẩm.
- **Đo lường và cải tiến:** theo dõi lỗi lọt ra môi trường thật, thời gian nhận phản hồi, độ ổn định của bộ kiểm thử và các sự cố lặp lại.

Ví dụ, một tổ chức có nhiều sản phẩm có thể thống nhất rằng mọi thay đổi đều phải chạy kiểm thử tự động phù hợp trong pipeline; thay đổi ảnh hưởng đến dữ liệu nhạy cảm phải có đánh giá bảo mật; lỗi mức nghiêm trọng cao phải được xử lý hoặc có người chịu trách nhiệm chấp nhận rủi ro trước khi phát hành.

Chiến lược cấp tổ chức không nên áp một bộ test case hoặc một ngưỡng giống nhau cho mọi sản phẩm. Một hệ thống xử lý thanh toán và một trang nội dung tĩnh có mức độ ảnh hưởng khác nhau. Tổ chức nên thống nhất nguyên tắc, cách quản trị và mức tối thiểu; từng sản phẩm cần được phép bổ sung biện pháp theo rủi ro của mình.

**Đầu ra thường có:** nguyên tắc chất lượng, chính sách kiểm thử, tiêu chuẩn phát hành, mô hình trách nhiệm, nền tảng dùng chung và bộ chỉ số theo dõi.

### 2.2. Cấp sản phẩm: bảo vệ chất lượng trong suốt vòng đời sản phẩm

Chiến lược cấp sản phẩm chuyển định hướng chung thành cách tiếp cận phù hợp với một sản phẩm cụ thể. Nó cần xem xét người dùng, nghiệp vụ, kiến trúc, dữ liệu, cách triển khai và hậu quả nếu sản phẩm hoạt động sai.

Trước hết, nhóm sản phẩm xác định các thuộc tính chất lượng quan trọng. Tùy bối cảnh, đó có thể là:

- **Tính đúng đắn chức năng:** kết quả nghiệp vụ, quy tắc tính toán và trạng thái dữ liệu phải chính xác.
- **Độ tin cậy và khả năng phục hồi:** hệ thống xử lý lỗi, gián đoạn dịch vụ và thử lại như thế nào.
- **Hiệu năng và khả năng mở rộng:** thời gian phản hồi, thông lượng và hành vi khi tải tăng.
- **Bảo mật và quyền riêng tư:** xác thực, phân quyền, bảo vệ dữ liệu và chống lạm dụng.
- **Khả năng sử dụng và tiếp cận:** người dùng có thể hoàn thành tác vụ rõ ràng, kể cả khi dùng công nghệ hỗ trợ.
- **Tương thích và khả năng vận hành:** hành vi trên thiết bị, trình duyệt, môi trường triển khai và khả năng giám sát.

Tiếp theo, nhóm đánh giá rủi ro theo khả năng xảy ra và mức độ ảnh hưởng. Một lỗi làm sai số tiền thanh toán thường cần ưu tiên cao hơn lỗi căn lề ít ảnh hưởng. Rủi ro cũng có thể đến từ thay đổi kiến trúc, tích hợp bên ngoài, dữ liệu lớn, phân quyền phức tạp hoặc lịch sử sự cố.

Từ đó, nhóm chọn danh mục kiểm thử phù hợp:

- Kiểm thử đơn vị và thành phần để phản hồi nhanh về logic cục bộ.
- Kiểm thử API, hợp đồng và tích hợp để xác minh giao tiếp giữa các thành phần hoặc dịch vụ.
- Kiểm thử hệ thống và đầu cuối để kiểm tra luồng quan trọng từ góc nhìn người dùng.
- Kiểm thử phi chức năng như hiệu năng, bảo mật, khả năng tiếp cận, tương thích và phục hồi.
- Kiểm thử thăm dò để tìm vấn đề khó mô tả trước bằng test case cố định.
- Theo dõi sau phát hành để phát hiện hành vi bất thường trong điều kiện sử dụng thực tế.

Chiến lược sản phẩm cũng quyết định cách duy trì môi trường, dữ liệu kiểm thử, dữ liệu giả lập, dịch vụ phụ thuộc và bộ hồi quy. Những quyết định này cần tính đến kiến trúc thực tế. Chẳng hạn, sản phẩm có nhiều dịch vụ độc lập có thể cần kiểm thử hợp đồng và kiểm thử tích hợp có chọn lọc; không nên dựa hoàn toàn vào các luồng đầu cuối dài và dễ lỗi.

**Đầu ra thường có:** hồ sơ rủi ro sản phẩm, thuộc tính chất lượng ưu tiên, danh mục kiểm thử, cách quản lý môi trường và dữ liệu, chiến lược tự động hóa, cùng tiêu chí theo dõi sau phát hành.

### 2.3. Cấp dự án: tổ chức kiểm thử cho một thay đổi có thời hạn

Chiến lược cấp dự án áp dụng cho một sáng kiến, đợt phát triển hoặc thay đổi có phạm vi và thời gian xác định. Dự án cần biến định hướng sản phẩm thành hoạt động có thể thực hiện và kiểm soát.

Nhóm dự án cần làm rõ:

1. **Mục tiêu và phạm vi:** thay đổi nào nằm trong dự án, phần nào không thuộc phạm vi, hệ thống và nhóm nào bị ảnh hưởng.
2. **Yêu cầu và rủi ro:** tiêu chí chấp nhận, luồng nghiệp vụ quan trọng, phụ thuộc bên ngoài, dữ liệu bị tác động và các tình huống thất bại.
3. **Cách tiếp cận kiểm thử:** kiểm thử ở cấp nào, loại kiểm thử nào cần thực hiện, phần nào tự động hóa và phần nào cần đánh giá thủ công.
4. **Nguồn lực và trách nhiệm:** ai chuẩn bị môi trường, dữ liệu, test case, ai xử lý lỗi và ai đưa ra quyết định chấp nhận rủi ro.
5. **Lịch và phụ thuộc:** thời điểm có bản dựng, tích hợp, kiểm thử hồi quy, kiểm thử người dùng và phát hành; các điều kiện có thể làm chậm tiến độ.
6. **Điều kiện bắt đầu và kết thúc:** đầu vào tối thiểu để kiểm thử có ý nghĩa và bằng chứng cần đạt trước khi chuyển giai đoạn hoặc phát hành.
7. **Phương án triển khai và phục hồi:** cách phát hành theo đợt, theo dõi, tắt tính năng hoặc quay lui nếu rủi ro xảy ra.

Ví dụ, dự án bổ sung phương thức thanh toán mới cần phối hợp với nhà cung cấp thanh toán, môi trường sandbox, dữ liệu giao dịch giả lập và nhóm vận hành. Chiến lược dự án phải chỉ rõ các luồng thành công, từ chối, hết thời gian chờ, gửi yêu cầu lặp lại và đối soát; đồng thời phân công người xác minh từng tích hợp.

Chiến lược dự án cần đủ cụ thể để nhóm có thể lập kế hoạch và theo dõi tiến độ, nhưng vẫn có thể điều chỉnh khi yêu cầu, rủi ro hoặc phụ thuộc thay đổi. Mọi thay đổi đáng kể về phạm vi nên dẫn đến việc xem xét lại mức độ kiểm thử.

**Đầu ra thường có:** phạm vi kiểm thử dự án, ma trận yêu cầu và kiểm thử, lịch kiểm thử, phân công trách nhiệm, điều kiện vào/ra, danh sách phụ thuộc và kế hoạch phát hành.

### 2.4. Cấp phạm vi kiểm thử: quyết định kiểm tra điều gì và bằng cách nào

Phạm vi kiểm thử là phần chức năng, thành phần, API, quy tắc nghiệp vụ hoặc thay đổi cụ thể đang được đánh giá. Đây là cấp gần nhất với việc thiết kế và thực thi kiểm thử.

Với mỗi phạm vi, người thực hiện cần xác định:

- **Đối tượng và ranh giới:** thành phần nào được kiểm tra, phần nào nằm ngoài phạm vi; phụ thuộc nào được giả lập.
- **Cơ sở kiểm thử:** yêu cầu, tiêu chí chấp nhận, thiết kế, hợp đồng API, quy tắc nghiệp vụ hoặc lỗi đã từng xảy ra.
- **Điều kiện và rủi ro:** điều kiện bình thường, biên, dữ liệu không hợp lệ, quyền truy cập, trạng thái trước đó và các tình huống cạnh tranh.
- **Kỹ thuật thiết kế:** phân vùng tương đương, giá trị biên, bảng quyết định, chuyển trạng thái, kiểm thử dựa trên rủi ro hoặc kiểm thử thăm dò.
- **Cách thực hiện:** kiểm thử thủ công hay tự động, ở cấp đơn vị, API, tích hợp hay giao diện; cần công cụ và dữ liệu nào.
- **Kết quả mong đợi và bằng chứng:** trạng thái, dữ liệu, mã phản hồi, thông báo, log hoặc sự kiện cần quan sát.
- **Truy vết và xử lý lỗi:** liên kết trường hợp kiểm thử với yêu cầu/rủi ro, ghi nhận kết quả và mô tả cách tái hiện lỗi.

Ví dụ, phạm vi kiểm thử cho quy tắc áp dụng mã giảm giá có thể bao gồm mã hợp lệ, mã hết hạn, đơn hàng dưới mức tối thiểu, sản phẩm bị loại trừ, mã đã sử dụng, hai mã cùng lúc và yêu cầu gửi lặp. Mỗi trường hợp cần có dữ liệu đầu vào và kết quả mong đợi rõ ràng. Với quy tắc tính tiền, nên kiểm tra cả giá trị sát ngưỡng và cách làm tròn.

Ở cấp này, cần tránh chỉ kiểm tra đường đi thành công. Những trường hợp biên, trạng thái lỗi, quyền hạn và hành vi khi phụ thuộc gián đoạn thường là nơi rủi ro bị bỏ sót.

**Đầu ra thường có:** danh sách điều kiện kiểm thử, test case hoặc charter kiểm thử thăm dò, dữ liệu kiểm thử, kết quả thực thi, lỗi được ghi nhận và bằng chứng liên quan.

## 3. Cách bốn cấp liên kết với nhau

Các cấp tạo thành một chuỗi chuyển hóa từ định hướng sang bằng chứng:

~~~mermaid
flowchart TD
    A["Tổ chức<br/>Nguyên tắc, chuẩn chung, khẩu vị rủi ro"]
    B["Sản phẩm<br/>Thuộc tính chất lượng, rủi ro và danh mục kiểm thử"]
    C["Dự án<br/>Phạm vi, lịch, nguồn lực và tiêu chí phát hành"]
    D["Phạm vi kiểm thử<br/>Điều kiện, dữ liệu, test case và bằng chứng"]
    A --> B
    B --> C
    C --> D
    D -. "Kết quả, lỗi và rủi ro còn lại" .-> C
    C -. "Xu hướng chất lượng và sự cố" .-> B
    B -. "Bài học và thay đổi rủi ro" .-> A
~~~

Ví dụ, tổ chức yêu cầu bảo vệ dữ liệu cá nhân. Ở cấp sản phẩm, nhóm xác định dữ liệu nào nhạy cảm và các luồng truy cập có rủi ro. Ở cấp dự án, thay đổi màn hình hồ sơ người dùng được đánh giá về phạm vi quyền truy cập và lịch kiểm thử bảo mật. Ở cấp phạm vi, người kiểm thử tạo các trường hợp truy cập bằng tài khoản đúng quyền, sai quyền, phiên hết hạn và yêu cầu trực tiếp đến API. Kết quả ở cấp phạm vi trở thành bằng chứng để dự án quyết định phát hành; nếu lỗi phân quyền xuất hiện lặp lại, sản phẩm và tổ chức cần xem xét lại biện pháp chung.

Khi chuyển từ cấp này sang cấp khác, hãy giữ lại mối liên hệ giữa **mục tiêu chất lượng → rủi ro → hoạt động kiểm thử → bằng chứng → quyết định**. Nếu một hoạt động không gắn với rủi ro hoặc mục tiêu rõ ràng, nhóm nên xem lại lý do thực hiện. Ngược lại, một rủi ro quan trọng chưa có biện pháp kiểm tra là dấu hiệu chiến lược còn thiếu.

## 4. Phân biệt phạm vi, cấp độ và loại kiểm thử

Ba khái niệm này thường bị dùng thay thế cho nhau nhưng trả lời các câu hỏi khác nhau:

| Khái niệm | Câu hỏi | Ví dụ |
|---|---|---|
| Phạm vi kiểm thử | Đang kiểm tra phần nào? | Quy tắc áp dụng mã giảm giá |
| Cấp độ kiểm thử | Kiểm tra ở mức cấu thành nào? | Đơn vị, tích hợp, hệ thống, chấp nhận |
| Loại kiểm thử | Đang đánh giá khía cạnh chất lượng nào? | Chức năng, hiệu năng, bảo mật, khả năng sử dụng |

Một phạm vi có thể được kiểm tra ở nhiều cấp độ và bằng nhiều loại kiểm thử. Với mã giảm giá, kiểm thử đơn vị có thể xác minh phép tính; kiểm thử API có thể xác minh hợp đồng và trạng thái phản hồi; kiểm thử đầu cuối có thể xác minh toàn bộ luồng thanh toán; kiểm thử hiệu năng có thể đánh giá hệ thống khi nhiều đơn hàng cùng áp dụng khuyến mãi.

Việc chọn cấp độ và loại kiểm thử phải dựa trên rủi ro, kiến trúc và mục tiêu. Không phải mọi chức năng đều cần một bộ kiểm thử đầu cuối giống nhau, và không phải mọi thuộc tính chất lượng đều có thể được xác minh bằng test case chức năng.

## 5. Xây dựng chiến lược kiểm thử theo từng bước

Một quy trình thực tế có thể triển khai theo các bước sau:

1. **Hiểu bối cảnh:** xác định người dùng, mục tiêu nghiệp vụ, kiến trúc, quy định, cách triển khai và hậu quả khi hệ thống sai.
2. **Xác định thuộc tính chất lượng:** chọn những thuộc tính quan trọng với sản phẩm hoặc thay đổi; mô tả chúng bằng tiêu chí có thể quan sát.
3. **Đánh giá và xếp hạng rủi ro:** xem xét khả năng xảy ra, mức độ ảnh hưởng, độ khó phát hiện và lịch sử sự cố. Ưu tiên luồng quan trọng và vùng thay đổi có nhiều phụ thuộc.
4. **Chọn cách kiểm thử:** xác định cấp độ, loại kiểm thử, kỹ thuật thiết kế, mức tự động hóa và phần cần kiểm thử thăm dò.
5. **Chuẩn bị điều kiện:** bảo đảm môi trường, dữ liệu, quyền truy cập, dịch vụ giả lập và công cụ đủ tin cậy để kết quả có ý nghĩa.
6. **Đặt tiêu chí quyết định:** xác định điều kiện bắt đầu, điều kiện kết thúc, lỗi không được chấp nhận, cách ghi nhận rủi ro còn lại và người có thẩm quyền quyết định.
7. **Theo dõi và điều chỉnh:** xem kết quả thực tế, lỗi lọt, sự cố sau phát hành và thay đổi phạm vi để cập nhật chiến lược.

Không nhất thiết mọi quyết định đều cần một tài liệu dài. Với thay đổi nhỏ, một ghi chú ngắn về rủi ro, phạm vi và bằng chứng cần có có thể đủ. Với sản phẩm quan trọng hoặc dự án có nhiều phụ thuộc, cần mô tả rõ hơn để các nhóm phối hợp nhất quán.

## 6. Ví dụ xuyên suốt: chiến lược kiểm thử cho chức năng thanh toán

Giả sử một nền tảng thương mại điện tử bổ sung chức năng thanh toán bằng ví điện tử. Cùng một mục tiêu chất lượng được diễn giải ở bốn cấp như sau:

| Cấp | Quyết định chiến lược | Bằng chứng mong đợi |
|---|---|---|
| Tổ chức | Giao dịch tài chính phải có tính toàn vẹn; thay đổi liên quan thanh toán phải qua kiểm soát bảo mật và có phương án xử lý sự cố. | Quy trình phê duyệt, kết quả kiểm thử bảo mật, log và dấu vết giao dịch. |
| Sản phẩm | Ưu tiên tính đúng đắn của số tiền, trạng thái giao dịch, xử lý thử lại, đối soát và khả năng phục hồi khi nhà cung cấp gián đoạn. | Bộ kiểm thử chức năng, tích hợp, bảo mật, phục hồi và giám sát sau phát hành. |
| Dự án | Kiểm tra tích hợp sandbox, luồng thành công/thất bại, timeout, callback lặp, đối soát và phát hành theo đợt. | Kết quả kiểm thử theo yêu cầu, xác nhận từ các bên phụ thuộc, tiêu chí phát hành và phương án quay lui. |
| Phạm vi | Kiểm tra API tạo giao dịch và xử lý callback với dữ liệu hợp lệ, chữ ký sai, callback trùng, giao dịch hết hạn và số tiền không khớp. | Test case có dữ liệu cụ thể, kết quả mong đợi, log đối chiếu và lỗi được truy vết. |

Ví dụ này cho thấy cùng một rủi ro có thể xuất hiện ở nhiều cấp. Tổ chức đặt nguyên tắc bảo vệ giao dịch; sản phẩm xác định các luồng và thuộc tính phải bảo vệ; dự án phân bổ hoạt động và nguồn lực; phạm vi kiểm thử xác minh hành vi cụ thể.

## 7. Tiêu chí bắt đầu, kết thúc và quyết định phát hành

Tiêu chí vào và ra giúp nhóm thống nhất khi nào một hoạt động kiểm thử có thể bắt đầu và khi nào bằng chứng đã đủ cho quyết định tiếp theo.

**Ví dụ về tiêu chí vào:**

- Bản dựng đúng phiên bản đã sẵn sàng và có thể triển khai vào môi trường kiểm thử.
- Yêu cầu hoặc tiêu chí chấp nhận đủ rõ để xác định kết quả mong đợi.
- Môi trường, dữ liệu và các phụ thuộc thiết yếu hoạt động.
- Các lỗi chặn việc kiểm thử đã được xử lý hoặc có cách cô lập được thống nhất.

**Ví dụ về tiêu chí ra:**

- Các kiểm thử gắn với rủi ro quan trọng đã chạy và đạt kết quả yêu cầu.
- Không còn lỗi nghiêm trọng chưa được xử lý hoặc chấp nhận theo quy trình.
- Kiểm thử hồi quy phù hợp đã hoàn tất; lỗi còn lại và giới hạn kiểm thử được ghi nhận.
- Có đủ log, báo cáo hoặc bằng chứng để người có trách nhiệm đánh giá rủi ro còn lại.
- Kế hoạch theo dõi, tắt tính năng hoặc quay lui đã sẵn sàng khi cần.

Không nên dùng một ngưỡng máy móc cho mọi thay đổi. Một lỗi giao diện nhỏ có thể được chấp nhận có điều kiện; lỗi có thể làm ghi nhận sai giao dịch hoặc lộ dữ liệu thường cần ngưỡng nghiêm ngặt hơn. Quyết định cuối cùng phải dựa trên tác động, bằng chứng và thẩm quyền đã thống nhất.

## 8. Đo lường để cải thiện chiến lược

Chỉ số có ích khi giúp nhóm phát hiện điểm yếu và đưa ra hành động. Có thể kết hợp:

- **Lỗi lọt ra môi trường thật:** số lượng, mức độ nghiêm trọng, phạm vi ảnh hưởng và nguyên nhân.
- **Mức bao phủ rủi ro quan trọng:** các rủi ro ưu tiên đã có hoạt động kiểm thử và bằng chứng hay chưa.
- **Thời gian phản hồi:** thời gian từ lúc thay đổi được tạo đến khi nhóm nhận được kết quả kiểm thử có ích.
- **Độ ổn định của kiểm thử tự động:** tỷ lệ kiểm thử thất bại không ổn định, thời gian chạy và tần suất phải sửa bộ kiểm thử.
- **Xu hướng lỗi theo giai đoạn:** lỗi được phát hiện ở review, kiểm thử đơn vị, tích hợp, chấp nhận hay sau phát hành.
- **Hiệu quả xử lý sự cố:** thời gian phát hiện, khôi phục và hoàn thành hành động ngăn tái diễn.

Độ bao phủ dòng lệnh hoặc số lượng test case có thể cung cấp tín hiệu, nhưng không tự chứng minh sản phẩm an toàn hay đáp ứng nghiệp vụ. Một bộ kiểm thử có độ bao phủ mã cao vẫn có thể bỏ sót quy tắc quan trọng nếu dữ liệu và khẳng định kết quả không phù hợp. Hãy đọc chỉ số cùng rủi ro, chất lượng test và tác động thực tế.

## 9. Những sai lầm thường gặp

- **Dùng một chiến lược chung cho mọi sản phẩm:** khiến hệ thống rủi ro cao thiếu kiểm soát hoặc hệ thống đơn giản phải gánh quy trình không cần thiết. Hãy giữ nguyên tắc chung và điều chỉnh theo hồ sơ rủi ro.
- **Chỉ viết chiến lược ở đầu dự án:** chiến lược nhanh chóng lỗi thời khi yêu cầu, kiến trúc hoặc phụ thuộc thay đổi. Cần xem xét lại ở các mốc quan trọng và sau sự cố.
- **Đồng nhất chiến lược với danh sách test case:** danh sách trường hợp không giải thích tại sao kiểm thử được chọn, rủi ro nào còn lại và ai quyết định phát hành.
- **Tự động hóa mọi thứ:** tự động hóa có chi phí xây dựng và bảo trì. Ưu tiên luồng lặp lại, quan trọng, có kết quả xác định; kết hợp kiểm thử thăm dò và đánh giá thủ công ở nơi phù hợp.
- **Phụ thuộc quá nhiều vào kiểm thử đầu cuối:** các luồng dài thường chậm và khó chẩn đoán. Phân bổ kiểm thử ở nhiều cấp để phát hiện lỗi gần nơi phát sinh.
- **Chạy kiểm thử nhưng không dùng kết quả để quyết định:** báo cáo chỉ có giá trị khi được liên kết với rủi ro, tiêu chí phát hành và hành động khắc phục.
- **Xem số liệu đẹp là bằng chứng chất lượng:** tỷ lệ pass cao hoặc độ bao phủ lớn không có ý nghĩa nếu các tình huống quan trọng chưa được kiểm tra.

## 10. Tự kiểm tra chiến lược

Trước khi thống nhất một chiến lược, nhóm có thể tự hỏi:

- Mục tiêu chất lượng và rủi ro quan trọng nhất đã được nêu rõ chưa?
- Các quyết định ở cấp dự án có phù hợp với nguyên tắc và chiến lược sản phẩm không?
- Mỗi rủi ro ưu tiên có hoạt động kiểm thử và bằng chứng tương ứng không?
- Môi trường, dữ liệu, công cụ và người phụ trách đã sẵn sàng chưa?
- Tiêu chí vào/ra và người quyết định phát hành đã rõ chưa?
- Rủi ro còn lại, giới hạn kiểm thử và kế hoạch theo dõi có được ghi nhận không?
- Có cơ chế cập nhật chiến lược khi thay đổi hoặc sự cố cung cấp thông tin mới không?

Một chiến lược tốt tạo ra sự nhất quán giữa mục tiêu chất lượng, mức rủi ro và hoạt động kiểm thử. Cấp tổ chức cung cấp định hướng; cấp sản phẩm xác định điều cần bảo vệ; cấp dự án tổ chức nguồn lực và quyết định; cấp phạm vi tạo ra bằng chứng cụ thể. Khi các cấp liên kết và phản hồi cho nhau, nhóm có thể tập trung công sức vào những rủi ro có ảnh hưởng lớn nhất và đưa ra quyết định phát hành dựa trên bằng chứng.
