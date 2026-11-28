# Regression test — Kiểm thử hồi quy yêu cầu bảo mật

## 1. Regression test bảo vệ điều gì sau một thay đổi?

**Regression testing — kiểm thử hồi quy** đánh giá xem một thay đổi có làm xuất hiện tác động bất lợi đối với những hành vi hoặc thuộc tính cần tiếp tục được bảo đảm hay không.

Trong module yêu cầu bảo mật, câu hỏi trọng tâm là:

> Sau khi sửa mã, đổi cấu hình, nâng thư viện hoặc chuyển môi trường, các yêu cầu bảo mật còn hiệu lực có tiếp tục được đáp ứng không?

Ví dụ, nhóm tối ưu tốc độ đọc hợp đồng bằng cache. Chức năng đọc của người có quyền vẫn hoạt động và nhanh hơn, nhưng đường xử lý cache hit vô tình bỏ qua kiểm tra quyền. Kiểm thử chức năng thông thường có thể đạt trong khi yêu cầu cách ly tenant đã bị vi phạm.

Theo [ISTQB CTFL Syllabus v4.0.1, mục 2.2.3](https://istqb.org/wp-content/uploads/2024/11/ISTQB_CTFL_Syllabus_v4.0.1.pdf), confirmation testing tập trung xác nhận lỗi gốc đã được sửa, còn regression testing tìm tác động bất lợi của thay đổi. Hồi quy có thể liên quan thành phần, hệ thống kết nối hoặc môi trường.

Bài học đặt hoạt động hồi quy trong chuỗi:

**Thay đổi → phân tích tác động → yêu cầu chịu ảnh hưởng → ca kiểm thử → bằng chứng → quyết định xử lý.**

Sau bài học, người học cần có thể:

- Phân biệt hồi quy với xác nhận bản sửa lỗi, smoke test và đánh giá bảo mật khám phá.
- Chọn phạm vi kiểm thử dựa trên yêu cầu, phụ thuộc và rủi ro.
- Tạo ca hồi quy từ một phát hiện bảo mật đã được xử lý.
- Kiểm tra cả hành vi được phép, bị cấm, dữ liệu và tác động nghiệp vụ.
- Quản lý dữ liệu thử, kết quả không ổn định và thay đổi baseline.
- Báo cáo đúng phần đã đánh giá và những khoảng trống còn lại.

## 2. Phân biệt các mục đích kiểm thử

| Hoạt động | Câu hỏi chính | Ví dụ trong bảo mật |
| --- | --- | --- |
| Confirmation testing | Lỗi cụ thể đã được sửa chưa? | Request từng đọc được hợp đồng tenant khác nay bị từ chối đúng |
| Regression testing | Thay đổi có làm hỏng nghĩa vụ cần duy trì không? | Sau tối ưu cache, cách ly tenant, quyền đọc và audit vẫn đúng |
| Smoke test | Bản triển khai có đủ hoạt động để đánh giá tiếp không? | Đăng nhập thử, API chính và phụ thuộc thiết yếu sẵn sàng |
| Kiểm thử chức năng mới | Chức năng vừa thêm có đúng đặc tả không? | Người dùng xuất được hợp đồng trong phạm vi đã cấp |
| Đánh giá bảo mật khám phá | Có điểm yếu hoặc đường gây hại chưa biết không? | Tìm đường tải tệp mới chưa được đưa vào mô hình quyền |
| Kiểm thử hiệu năng | Hệ thống đáp ứng điều kiện tải đã định không? | Độ trễ và tài nguyên khi nhiều người cùng truy cập |

Một ca có thể được dùng cho nhiều mục đích ở những thời điểm khác nhau. Ca tái hiện lỗi được dùng để xác nhận bản sửa hôm nay; sau đó được giữ trong bộ hồi quy cho các thay đổi tiếp theo.

Regression là **mục đích đánh giá**, không phải một tầng duy nhất. Có thể có ca hồi quy ở mức hàm, thành phần, tích hợp API, luồng đầu cuối hoặc cấu hình triển khai.

Bộ smoke chạy thành công không thay cho hồi quy các yêu cầu quan trọng. Một ứng dụng có thể khởi động, đăng nhập và đọc dữ liệu được nhưng vẫn cho phép truy cập trái quyền.

## 3. Chọn đối tượng bảo vệ: yêu cầu và thuộc tính ổn định

Bộ hồi quy cần bám vào những nghĩa vụ còn hiệu lực. Không nên chỉ lưu lại các thao tác UI hoặc bản chụp phản hồi mà không biết chúng đang bảo vệ điều gì.

Giả sử một hệ thống quản lý hợp đồng nhiều tenant có IdP, API, kho tệp, tác vụ xuất dữ liệu, logging và backup.

| Mã yêu cầu minh họa | Nghĩa vụ cần duy trì | Hướng kiểm thử hồi quy |
| --- | --- | --- |
| SR-AUTH-01 | Hành động quản trị chỉ được thực hiện với bằng chứng xác thực đáp ứng chính sách đã xác định | Phiên đủ điều kiện được phép; phiên thiếu điều kiện không tạo tác động |
| SR-TENANT-02 | Chủ thể chỉ được đọc hợp đồng khi thuộc đúng tenant và có quan hệ quyền được phép | Ca đúng quyền, chéo tenant, cùng tenant nhưng không có quyền |
| SR-DATA-03 | Dữ liệu hợp đồng và các bản sao thuộc phạm vi được bảo vệ theo baseline | Đối chiếu vị trí lưu, cấu hình bảo vệ và quyền tiếp cận |
| SR-LOG-04 | Thay đổi hợp đồng có sự kiện audit cần thiết và không ghi bí mật bị cấm | Đối chiếu thao tác với sự kiện; kiểm tra dữ liệu thử đánh dấu |
| SR-REC-05 | Phục hồi chức năng và dữ liệu theo RTO/RPO đã xác nhận | Đánh giá phục hồi trên phạm vi thay đổi liên quan |

Các yêu cầu trong bảng là khung ví dụ. Để chạy kiểm thử thực tế, phải có phạm vi, tham số và tiêu chí cụ thể, không chỉ mã yêu cầu.

### Thuộc tính ổn định khác chi tiết triển khai

Thuộc tính cần giữ có thể là:

- Người không có quyền không nhận được nội dung hợp đồng.
- Yêu cầu bị từ chối không thay đổi trạng thái nghiệp vụ.
- Người có quyền vẫn thực hiện được chức năng.
- Token truy cập không xuất hiện trong các trường log thuộc phạm vi.
- Dữ liệu phục hồi giữ quan hệ tenant và quyền đúng theo yêu cầu.

Tên hàm nội bộ, vị trí một nút hoặc thứ tự các trường JSON có thể đổi mà các thuộc tính trên vẫn đúng. Bộ kiểm thử quá phụ thuộc chi tiết không liên quan sẽ tạo nhiều lỗi giả và khó duy trì.

Ngược lại, không được bỏ kiểm tra một trường chỉ vì nó thường thay đổi nếu trường đó có ý nghĩa bảo mật, như tenantId, ownerId hoặc quyết định quyền.

## 4. Những thay đổi nào cần được phân tích?

Hồi quy bảo mật không chỉ áp dụng khi sửa trực tiếp lớp bảo mật.

| Thay đổi | Tác động bảo mật có thể xuất hiện | Phần nên xem xét |
| --- | --- | --- |
| Refactor truy vấn hoặc thêm cache | Bỏ lọc tenant, bỏ kiểm tra quyền trên cache hit | Đọc chi tiết, danh sách, tải tệp và quyền thay đổi |
| Đổi IdP hoặc ánh xạ claim | Nhầm tenant, vai trò, phạm vi phiên | Xác thực tích hợp, phân quyền và thu hồi |
| Nâng thư viện framework | Đổi mặc định, thứ tự middleware hoặc cách xử lý request | Tuyến API, cơ chế từ chối và điều kiện phụ trợ |
| Đổi serializer hoặc DTO | Lộ trường trước đây không trả | Hợp đồng dữ liệu và quyền thuộc tính |
| Đổi logging | Mất audit, ghi token hoặc nội dung nhạy cảm | Lược đồ sự kiện, che giảm dữ liệu và chuyển log |
| Thêm tác vụ nền | Mất ngữ cảnh người yêu cầu hoặc tenant | Phạm vi ủy quyền và quyền tại thời điểm bàn giao |
| Chuyển storage hoặc đổi quyền hạ tầng | Tệp tải trực tiếp hoặc backup có quyền rộng hơn | Cấu hình triển khai và đường dữ liệu |
| Migration dữ liệu | Gán sai tenant, quan hệ quyền hoặc giá trị mặc định | Dữ liệu trước/sau và các chức năng đọc/ghi |
| Đổi backup hoặc quy trình phục hồi | Không khôi phục được khóa, quyền hoặc dữ liệu nhất quán | Chức năng phục hồi và RTO/RPO liên quan |
| Sửa pipeline hoặc feature flag | Bản được đánh giá khác bản chạy thật | Cấu hình, artifact và phạm vi bật chức năng |

Một thay đổi nhỏ có thể ảnh hưởng một thành phần dùng chung rất rộng. Ngược lại, không phải mọi thay đổi đều cần chạy lại mọi bài diễn tập tốn kém.

Quyết định cần dựa vào **đường phụ thuộc và hậu quả**, không chỉ số dòng mã hoặc tên thư mục.

### Đầu ra của phân tích tác động

Nên ghi:

1. Thành phần, dữ liệu và cấu hình thay đổi.
2. Yêu cầu trực tiếp chịu ảnh hưởng.
3. Những người sử dụng hoặc thành phần phụ thuộc gián tiếp.
4. Các lỗi trước đây có cùng nguyên nhân hoặc cùng đường xử lý.
5. Những ca sẽ chạy và lý do lựa chọn.
6. Phần chưa đánh giá, bằng chứng có thể tái sử dụng và lý do.
7. Điều kiện khiến phải mở rộng phạm vi.

Nếu chưa hiểu rõ phạm vi phụ thuộc, cần điều tra thêm hoặc chọn mức kiểm thử rộng hơn phù hợp với rủi ro. Không coi “không biết ảnh hưởng gì” là “không có ảnh hưởng”.

## 5. Xây dựng bộ hồi quy dựa trên rủi ro

### 5.1. Các nguồn hình thành ca hồi quy

- Tiêu chí kiểm chứng của yêu cầu đang có hiệu lực.
- Phát hiện bảo mật đã được xác nhận và sửa.
- Lỗi vận hành, sự cố và kết quả điều tra nguyên nhân.
- Kịch bản đe dọa quan trọng.
- Điều kiện phê duyệt vận hành hoặc giới hạn cấu hình.
- Thay đổi dữ liệu, tích hợp và giả định kiến trúc.

[OWASP SAMM — Requirements-driven Testing](https://owaspsamm.org/model/verification/requirements-driven-testing/) gắn kiểm thử với yêu cầu bảo mật và việc xây dựng dần các ca hồi quy. Hoạt động này cần cả trường hợp đúng và tình huống sử dụng sai.

### 5.2. Ưu tiên theo hậu quả và khả năng phát hiện

| Nhóm ưu tiên minh họa | Tiêu chí | Ví dụ |
| --- | --- | --- |
| Trọng yếu | Vi phạm gây lộ dữ liệu, vượt quyền hoặc mất khả năng bảo vệ cốt lõi | Chéo tenant, cấp quyền trái phép, bỏ kiểm tra xác thực |
| Theo tác động thay đổi | Liên quan trực tiếp hoặc qua phụ thuộc dùng chung | Cache thay đổi thì đánh giá các đường đọc có dùng cache |
| Hồi quy mở rộng | Cần nhiều thành phần, dữ liệu hoặc thời gian hơn | Thu hồi trên nhiều nút, tác vụ nền, migration |
| Theo môi trường hoặc tình huống đặc biệt | Khó thực hiện trong mỗi lần tích hợp | Phục hồi, mất phụ thuộc, thay vùng triển khai |

Đây là cách phân nhóm thực hành, không phải cấp độ chuẩn bắt buộc.

Ưu tiên không đồng nghĩa bỏ nghĩa vụ chưa chạy. Phần được hoãn cần xuất hiện trong kế hoạch và báo cáo với người chịu trách nhiệm, thay vì biến mất khỏi kết luận.

### 5.3. Kết hợp ca nhanh với ca có ngữ cảnh thực

Kiểm tra hàm quyết định quyền giúp bao phủ nhiều tổ hợp nhanh. Kiểm tra API giúp xác nhận tuyến xử lý thật có thực thi quyết định đó. Kiểm tra cấu hình triển khai có thể phát hiện một tuyến hoặc storage bị mở ngoài đường đã thử.

Không thay toàn bộ kiểm thử tích hợp bằng việc giả lập một hàm bảo mật luôn trả kết quả mong đợi. Làm như vậy có thể kiểm tra được logic nghiệp vụ xung quanh nhưng không còn đánh giá cơ chế bảo vệ đang được thay đổi.

## 6. Biến một lỗi bảo mật thành ca hồi quy có giá trị

### 6.1. Từ hiện tượng đến thuộc tính cần bảo vệ

Một ca hồi quy tốt không chỉ ghi “gửi lại request từng gây lỗi”. Nó cần giữ được nguyên nhân quan trọng và kết quả bảo vệ cần duy trì.

Quy trình có thể gồm:

1. Xác nhận phát hiện và điều kiện tái hiện.
2. Xác định yêu cầu bị vi phạm.
3. Làm rõ nguyên nhân đủ để chọn phạm vi kiểm thử.
4. Tạo fixture tối thiểu nhưng vẫn thể hiện điều kiện gây lỗi.
5. Định nghĩa kết quả đạt/không đạt độc lập với mã sửa.
6. Xác nhận ca có khả năng phát hiện vi phạm trong điều kiện thử.
7. Giữ ca cùng thông tin truy vết cho các thay đổi sau.

[NIST SSDF 1.1, nhóm RV.3](https://nvlpubs.nist.gov/nistpubs/SpecialPublications/NIST.SP.800-218.pdf) đề cập phân tích nguyên nhân, xem xét điểm yếu tương tự và điều chỉnh quy trình để giảm tái diễn. Khi tạo ca hồi quy, cần xem xét lớp lỗi liên quan thay vì chỉ một đầu vào tình cờ.

### 6.2. Đánh giá khả năng phát hiện của ca thử

Trong môi trường đánh giá có kiểm soát, có thể xác nhận ca tái hiện thất bại trên bản còn lỗi và đạt sau khi sửa. Nếu không thể chạy bản cũ, cần có bằng chứng khác cho thấy điểm quan sát phân biệt được hành vi đúng và sai.

Điều cần kiểm tra là ca thất bại vì **vi phạm bảo mật cần phát hiện**, không phải vì thiếu dữ liệu, sai token hoặc lỗi môi trường.

Với một số kiểm soát trọng yếu, có thể dùng biến thể có kiểm soát của thành phần trong môi trường thử để xác nhận bộ kiểm thử nhận ra thiếu kiểm soát. Đây là kỹ thuật tùy chọn, cần giới hạn phạm vi; không phải yêu cầu phải thay đổi mọi triển khai để chứng minh mọi ca.

### 6.3. Giữ ý nghĩa thay vì khóa vào một bản vá

Nếu bản sửa dùng một hàm kiểm tra quyền mới, ca hồi quy nên kiểm tra người không có quyền không đọc được dữ liệu. Chỉ kiểm tra rằng “hàm X được gọi một lần” có thể bỏ sót trường hợp kết quả từ chối bị bỏ qua.

Kiểm tra tương tác nội bộ vẫn có thể hữu ích ở tầng thành phần, nhưng không thay thế bằng chứng về kết quả bảo vệ tại đường truy cập có rủi ro.

## 7. Ví dụ xuyên suốt: lỗi cách ly tenant tái xuất hiện qua cache

### 7.1. Bối cảnh

Hệ thống quản lý hợp đồng có chính sách:

- Người dùng chỉ được đọc hợp đồng thuộc tenant của mình.
- Trong tenant đó, người dùng phải có quan hệ Reader hoặc Owner đối với hợp đồng.
- API chi tiết trong ví dụ trả 403 khi người dùng đã xác thực nhưng thiếu quyền.
- Phản hồi từ chối không được chứa nội dung hoặc liên kết tải có hiệu lực của hợp đồng.

Fixture:

| Thành phần | Giá trị mẫu |
| --- | --- |
| userA | Thuộc tenant A, được đọc contractA |
| userA2 | Thuộc tenant A, không có quyền với contractA |
| userB | Thuộc tenant B, được đọc contractB |
| contractA | Tenant A, có chuỗi dữ liệu mẫu riêng để nhận diện |
| contractB | Tenant B, có dữ liệu mẫu khác contractA |

Các danh tính đều có phiên hoặc token hợp lệ trong môi trường thử.

### 7.2. Lỗi ban đầu và cách sửa

Phát hiện **BUG-SEC-018** trong ví dụ: sau khi userA đọc contractA, userB gọi cùng API và nhận được nội dung từ cache. Đường cache miss có kiểm tra quyền nhưng đường cache hit trả kết quả trước khi kiểm tra.

Nguyên nhân cần bảo vệ là **một đường trả nội dung bỏ qua thực thi quyền**. Việc cache dữ liệu theo mã đối tượng tự nó không nhất thiết sai; dữ liệu dùng chung vẫn có thể được cache nếu quyền được thực thi đúng cho từng lần cung cấp nội dung.

Bản sửa bảo đảm các đường trả dữ liệu đều tuân thủ SR-TENANT-02.

### 7.3. Ca hồi quy REG-TENANT-CACHE-01

~~~text
Yêu cầu: SR-TENANT-02
Nguồn: BUG-SEC-018
Mục tiêu:
Không trả nội dung contractA cho userB sau khi cache đã được làm nóng.

Chuẩn bị:
- Tạo hai tenant và các hợp đồng mẫu.
- Cấp đúng quan hệ Reader/Owner cho userA và userB.
- Xác nhận userB đọc được contractB.
- Đưa cache thử về trạng thái xác định.

Thực hiện:
1. userA đọc contractA và nhận nội dung đúng.
2. Xác nhận đường đọc tiếp theo sử dụng trạng thái cache cần đánh giá.
3. userB đọc contractA bằng phiên hợp lệ của userB.
4. userA đọc lại contractA.

Kỳ vọng:
- Bước 1 và 4 được phép, dữ liệu đúng hợp đồng.
- Bước 3 trả 403 theo hợp đồng của ví dụ.
- Bước 3 không có nội dung, trường bị hạn chế hoặc liên kết tải
  có hiệu lực của contractA.

Bằng chứng:
Request đã loại thông tin xác thực, phản hồi đã giảm dữ liệu,
trạng thái fixture và thông tin quan sát cache của môi trường thử.
~~~

Bước 2 phải có cơ sở phù hợp để biết ca đang đánh giá đường cache hit. Một request đọc thành công chưa chắc đã làm nóng đúng loại cache hoặc đúng nút xử lý.

Không bắt buộc lộ chi tiết cache cho client thật. Hạ tầng thử có thể cung cấp quan sát hoặc cách điều khiển thích hợp.

### 7.4. Tại sao cần nhiều tình huống liên quan?

| Biến thể | Điều muốn phát hiện |
| --- | --- |
| Cache chưa có dữ liệu, userB đọc contractA | Đường tải dữ liệu gốc thiếu kiểm tra quyền |
| Cache đã có dữ liệu, userB đọc contractA | Đường cache hit bỏ qua kiểm tra |
| userA2 cùng tenant nhưng không có quan hệ quyền | Chỉ kiểm tra tenant mà quên quyền đối tượng |
| userA đọc lại contractA | Bản sửa không chặn cả người có quyền |
| Quyền userA bị thu hồi khi cache còn dữ liệu | Kết quả quyền hoặc dữ liệu cũ làm kéo dài quyền |
| Đọc qua tải tệp hoặc bản xuất dùng thành phần chung | Lỗi cùng nguyên nhân ở đường khác |
| Đọc qua các nút xử lý thuộc cấu hình triển khai | Cache cục bộ hoặc cấu hình không đồng nhất |

Không cần mỗi biến thể là một bài đầu cuối dài. Có thể phân bổ chúng vào các tầng kiểm thử phù hợp, miễn bằng chứng tổng thể bao phủ đường có rủi ro.

### 7.5. Thay đổi tiếp theo làm lỗi có thể tái xuất hiện

Sau vài bản phát hành, nhóm tối ưu cache hoặc thay mapper phản hồi. Nếu đường mới trả payload trước kiểm tra quyền, REG-TENANT-CACHE-01 phải tiếp tục phát hiện.

Ca hồi quy không cần biết bản tối ưu dùng thư viện nào. Nó giữ điều kiện gây lỗi và kiểm tra đúng kết quả bảo vệ.

## 8. Thiết kế oracle: biết điều gì là kết quả đúng

**Oracle kiểm thử** là cơ sở để xác định kết quả mong đợi. Với hồi quy bảo mật, đó thường là yêu cầu, chính sách, lược đồ dữ liệu và quy tắc nghiệp vụ đã được xác nhận.

### 8.1. Kết hợp hành vi được phép và bị cấm

Nếu chỉ kiểm tra ca âm, hệ thống từ chối mọi người có thể được coi là an toàn. Nếu chỉ kiểm tra ca dương, đường vượt quyền có thể không bị phát hiện.

| Nghĩa vụ | Ca được phép | Ca bị cấm hoặc lỗi cần kiểm tra |
| --- | --- | --- |
| Xác thực quản trị | Phiên đáp ứng chính sách thực hiện được hành động | Thiếu bằng chứng xác thực cần thiết thì không có tác động |
| Cách ly tenant | Người có quyền đọc đúng hợp đồng | Người tenant khác hoặc thiếu quan hệ bị từ chối |
| Bảo vệ trường dữ liệu | Vai trò phù hợp nhận được trường được phép | Vai trò không đủ quyền không nhận trường hạn chế |
| Logging | Thao tác thành công tạo sự kiện đúng | Lỗi/ngoại lệ không làm ghi token hoặc bỏ mất sự kiện bắt buộc |
| Phục hồi | Dịch vụ và dữ liệu được sử dụng đúng sau khôi phục | Không làm sống lại quyền hoặc cấu hình đã bị loại bỏ |

### 8.2. Kiểm tra tác động, không chỉ phản hồi

Với thao tác thay đổi hợp đồng, phản hồi lỗi chưa đủ nếu dữ liệu đã bị sửa.

Có thể cần đối chiếu:

- Trạng thái trước/sau và phiên bản bản ghi.
- Người thực hiện được ghi nhận.
- Sự kiện nghiệp vụ.
- Outbox, tác vụ nền và thông báo.
- Sự kiện audit cần thiết.

Không đặt điều kiện “không có bất kỳ tác động nào” nếu yêu cầu đòi ghi audit từ chối. Cần phân biệt tác động nghiệp vụ bị cấm với tác động an ninh được mong đợi.

### 8.3. Tránh phụ thuộc vào lỗi không liên quan

Một ca phân quyền âm nhận 400 do payload sai không chứng minh quyền đã được kiểm tra. Token bị sửa làm xác thực thất bại cũng chưa đánh giá được quyền của người đã đăng nhập.

Chuẩn bị request có cấu trúc hợp lệ, danh tính hợp lệ và tài nguyên tồn tại. Hợp đồng phản hồi phải cụ thể; không dùng “mọi lỗi đều được coi là từ chối đúng”.

### 8.4. Snapshot có giới hạn

So sánh snapshot có thể hữu ích cho hợp đồng phản hồi, nhưng không nên là oracle duy nhất của thuộc tính bảo mật.

Có thể chuẩn hóa các trường biến động không liên quan như mã tương quan được sinh ngẫu nhiên. Không loại tenant, chủ sở hữu, quyền hoặc các trường nhạy cảm khỏi so sánh chỉ để tránh snapshot thay đổi.

Với dữ liệu bị cấm, kiểm tra lược đồ cho phép và nội dung có ý nghĩa. Chỉ tìm một chuỗi đánh dấu có thể bỏ sót việc lộ dữ liệu qua một biểu diễn hoặc trường khác.

## 9. Dữ liệu thử, thời gian và bất đồng bộ

### 9.1. Fixture phải ổn định nhưng có đủ đối chứng

Một fixture hồi quy nên:

- Có dữ liệu được phép và không được phép nhìn thấy.
- Dùng ít nhất các danh tính cần để phân biệt phạm vi.
- Có trạng thái ban đầu rõ ràng.
- Không phụ thuộc dữ liệu khách hàng thật.
- Không bị ca khác thay đổi ngoài kiểm soát.
- Có cách dọn dữ liệu khi ca thành công hoặc thất bại.

Với các ca chạy song song, dùng vùng dữ liệu hoặc định danh riêng phù hợp. Không để một ca xóa hợp đồng mà ca khác đang dùng để kiểm tra quyền đọc.

Không dùng chung một tài khoản quản trị cho mọi ca rồi chỉ đổi tên người dùng trong payload. Danh tính thực tế phải tương ứng điều kiện quyền được đánh giá.

### 9.2. Kiểm soát thời gian theo đúng nghĩa của yêu cầu

Giả sử có yêu cầu thu hồi quyền trong tối đa 60 giây sau khi thay đổi được xác nhận. Đây là ngưỡng minh họa, không phải mặc định của tiêu chuẩn.

Ở tầng thành phần, đồng hồ có thể điều khiển được giúp kiểm tra các mốc trước, tại và sau giới hạn. Ở tầng tích hợp, cần đánh giá cơ chế thực tế của token, cache và các nút xử lý.

Điều khiển đồng hồ trong một thành phần không tự chứng minh IdP hoặc cache bên ngoài đã hành xử theo thời gian đó.

Các điểm đo và sai số phải rõ. Không cộng thêm một khoảng chờ tùy ý rồi tuyên bố yêu cầu tối đa 60 giây đã đạt nếu thực tế chưa đo được khi nào quyền ngừng có hiệu lực.

### 9.3. Chờ sự kiện theo điều kiện thay vì ngủ tùy ý

Với audit hoặc tác vụ xuất:

1. Gắn mã tương quan riêng.
2. Biết điểm nào chứng minh xử lý đã hoàn tất.
3. Chờ theo điều kiện với giới hạn đã xác định.
4. Kiểm tra dữ liệu, sự kiện và tác động thuộc phạm vi.
5. Ghi lại thời gian và lỗi nếu điều kiện không xuất hiện.

Nếu yêu cầu cấm trả dữ liệu trái quyền, không được retry đến khi hệ thống cuối cùng từ chối rồi bỏ qua một lần trước đó đã trả dữ liệu. Một vi phạm đã quan sát được không biến mất vì lần thử sau đạt.

### 9.4. Kiểm tra vòng đời dữ liệu đúng phạm vi

Một ca có thể điều khiển thời gian để đánh giá logic xóa tệp tạm. Nhưng tự gọi tác vụ xóa không chứng minh bộ lập lịch thật sẽ chạy đúng hạn trong vận hành.

Cần phân biệt bằng chứng về:

- Logic chọn và xóa đúng dữ liệu.
- Lập lịch, retry và xử lý lỗi.
- Thời hạn thực tế.
- Bản sao và vị trí dữ liệu thuộc phạm vi.

Mức phối hợp kiểm thử phụ thuộc yêu cầu và thay đổi đang đánh giá.

## 10. Phạm vi môi trường, nâng cấp và phục hồi

### 10.1. Bộ thử phải phù hợp cấu hình triển khai

Ghi rõ bản phần mềm, phiên bản yêu cầu, policy, feature flag, cấu hình danh tính, storage và phụ thuộc có ảnh hưởng.

Nếu kiểm thử với một feature flag nhưng phát hành bằng cấu hình khác, kết quả chỉ hỗ trợ phần đã thực sự đánh giá. Cần xác định cấu hình nào là bắt buộc và các tổ hợp được hỗ trợ.

Không chỉ kiểm tra mã ở nhánh chính rồi suy rằng mọi nhánh bảo trì hoặc phiên bản đang phục vụ khách hàng đều đã có bằng chứng tương đương.

### 10.2. Migration dữ liệu có thể tạo hồi quy quyền

Sau migration, cần đánh giá các thuộc tính như tenant, chủ sở hữu, quan hệ Reader/Owner và trạng thái xóa.

Một schema hợp lệ chưa chứng minh dữ liệu đã được gán đúng quyền. Nên có mẫu trước/sau với trường hợp được phép và bị cấm để phát hiện sai lệch phân bổ.

Nếu nhiều phiên bản client hoặc dịch vụ còn được hỗ trợ, chọn các tổ hợp tương thích theo phân tích tác động. Không mặc định chỉ dùng tổ hợp phiên bản mới nhất là đủ.

### 10.3. Rollback và phục hồi cũng là thay đổi

Quay lui về một bản có lỗ hổng đã biết có thể làm mất kiểm soát vừa sửa. Kế hoạch rollback cần xét phiên bản phần mềm, dữ liệu, cấu hình và các yêu cầu còn hiệu lực.

Đối với SR-REC-05, một diễn tập có thể cần xác minh:

- Dịch vụ hoạt động và dữ liệu nhất quán theo phạm vi.
- Quyền và tenant không bị gán lại sai.
- Khóa và cấu hình cần thiết được khôi phục đúng quyền.
- RTO/RPO được đo bằng các mốc đã thống nhất.
- Không khôi phục ngoài ý muốn một chức năng hoặc cơ chế xác thực đã ngừng.

**RTO** là mục tiêu thời gian khôi phục hoạt động; **RPO** là mục tiêu về khoảng mất dữ liệu có thể chấp nhận, thể hiện bằng thời gian. Kết quả “backup thành công” không thay thế bằng chứng phục hồi.

Không cần diễn tập toàn bộ cho mọi lần sửa giao diện. Những thay đổi chạm vào backup, dữ liệu, khóa, quyền hoặc quy trình phục hồi cần được phân tích để chọn mức đánh giá phù hợp.

## 11. Tổ chức thực thi trong CI/CD

### 11.1. Phân lớp theo thời gian phản hồi và mức rủi ro

Một cách tổ chức minh họa:

| Giai đoạn | Phạm vi điển hình | Mục đích |
| --- | --- | --- |
| Trong thay đổi mã | Ca nhanh của thành phần và yêu cầu bị ảnh hưởng | Phản hồi sớm về lỗi dễ tái hiện |
| Tích hợp | Ca API và phụ thuộc thiết yếu | Xác nhận các thành phần cùng thực thi kiểm soát |
| Trước phát hành | Bộ trọng yếu, cấu hình triển khai và phần mở rộng theo tác động | Có bằng chứng cho artifact và cấu hình sẽ được sử dụng |
| Đánh giá theo điều kiện phù hợp | Tải, nhiều nút, migration hoặc phục hồi | Kiểm tra tình huống cần môi trường và dữ liệu riêng |

Đây là thiết kế quy trình tham khảo. Không có một lịch chạy hoặc số lượng ca chung phù hợp mọi hệ thống.

Các ca trọng yếu cần được thực hiện ở điểm đủ sớm để kết quả có thể tác động đến quyết định phát hành. Chạy sau khi thay đổi đã mở rộng dữ liệu thật không thay thế việc đánh giá trước đó.

### 11.2. Chọn ca theo tác động nhưng giữ phần bảo vệ cốt lõi

Có thể kết hợp:

- Bộ trọng yếu được duy trì cho các đường gây hậu quả lớn.
- Các ca liên quan trực tiếp đến thành phần thay đổi.
- Các ca của phụ thuộc hoặc người sử dụng thành phần chung.
- Ca từ các lỗi cùng nguyên nhân.
- Phạm vi mở rộng khi phân tích tác động chưa đủ tin cậy.

Không chỉ chọn theo tên file nguồn. Một thay đổi cấu hình ánh xạ vai trò có thể ảnh hưởng nhiều endpoint mà không sửa file controller nào.

Nếu cơ chế chọn ca tự động chưa hiểu một thay đổi, không nên mặc định chọn rỗng. Cần có quy tắc xử lý và khả năng xem xét phạm vi.

### 11.3. Gắn kết quả với đúng artifact

Kết quả cần liên kết đến:

- Bản phần mềm hoặc định danh artifact được đánh giá.
- Phiên bản cấu hình và policy.
- Phiên bản ma trận yêu cầu và bộ kiểm thử.
- Môi trường và dữ liệu thử quan trọng.
- Tham số chạy và các phần bị bỏ qua.
- Kết quả cùng hiện vật hỗ trợ.

Nếu build lại tạo artifact khác hoặc cấu hình triển khai thay đổi, cần xác định bằng chứng còn phù hợp đến đâu. Không chỉ dùng nhãn “build xanh” mà thiếu đối tượng được đánh giá.

### 11.4. Điều kiện chặn và ngoại lệ

Tiêu chí chặn cần dựa vào yêu cầu, tác động và quy trình quản lý rủi ro của tổ chức. Ví dụ, một ca xác nhận lộ dữ liệu chéo tenant không được che bởi hàng trăm ca khác đạt.

Nếu cần ngoại lệ, ghi yêu cầu chưa đáp ứng, phạm vi, rủi ro, điều kiện hạn chế, người có thẩm quyền và thời hạn xem xét. Quyết định ngoại lệ không biến ca thất bại thành đạt.

Đối với ca bị chặn hoặc chưa chạy, cần kết luận rõ phần bằng chứng còn thiếu và cách xử lý trước khi dựa vào nó để phát hành.

## 12. Xử lý test không ổn định và kết quả bất thường

**Flaky test** thường được dùng để nói về ca có kết quả không ổn định trong điều kiện tưởng như không đổi. Cần điều tra nguyên nhân thay vì coi mọi thất bại chập chờn là lỗi của kiểm thử.

### 12.1. Phân loại trước khi quyết định

| Nhóm nguyên nhân | Ví dụ | Hướng xử lý |
| --- | --- | --- |
| Sản phẩm có hành vi không ổn định | Một nút dùng quyền cũ, có race trong kiểm tra | Ghi phát hiện sản phẩm và tái hiện có kiểm soát |
| Fixture hoặc cách ly kém | Ca khác đổi quyền hoặc xóa dữ liệu | Sửa chuẩn bị và tách trạng thái |
| Quan sát sai thời điểm | Audit chưa qua hết pipeline | Định nghĩa ranh giới hoàn tất và chờ phù hợp |
| Môi trường lỗi | IdP thử không hoạt động, storage không sẵn sàng | Ghi trạng thái bị chặn hoặc lỗi môi trường |
| Kỳ vọng đã lỗi thời | Yêu cầu được sửa hợp lệ nhưng test chưa cập nhật | Đối chiếu baseline và cập nhật có truy vết |
| Kiểm thử quá phụ thuộc chi tiết | Snapshot khác timestamp không liên quan | Giữ các assertion có ý nghĩa, chuẩn hóa phần thích hợp |

Một lỗi chỉ xảy ra trên một nút hoặc trong một thứ tự request cụ thể vẫn có thể là lỗi bảo mật thật.

### 12.2. Retry không được xóa dấu vết thất bại

Chạy lại có thể hỗ trợ chẩn đoán, nhưng report phải giữ lần thất bại và điều kiện đi kèm.

Với vi phạm như đọc được dữ liệu tenant khác, một lần quan sát đã có giá trị. Không đổi kết luận sang đạt chỉ vì lần chạy sau không tái hiện.

Nếu dùng retry cho một thao tác chờ phụ thuộc hợp lệ, phải phân biệt rõ chờ điều kiện cho phép với việc bỏ qua một kết quả vi phạm đã xuất hiện.

### 12.3. Quarantine cần người chịu trách nhiệm

Tạm tách ca gây nhiễu khỏi một pipeline có thể là lựa chọn vận hành, nhưng phải làm rõ:

- Yêu cầu nào mất bằng chứng tự động.
- Nguyên nhân hoặc giả thuyết đang điều tra.
- Người xử lý và hạn xem xét.
- Bằng chứng thay thế nếu cần.
- Tác động đến tiêu chí phát hành.

Một ca disabled không được tính là pass. Với kiểm soát trọng yếu, cần xử lý khoảng trống bằng chứng theo rủi ro, thay vì để ca bị tách vô thời hạn.

## 13. Bảo trì bộ hồi quy khi yêu cầu thay đổi

### 13.1. Không phải hành vi cũ nào cũng phải giữ

Nếu yêu cầu được sửa theo quyết định hợp lệ, ca mong đợi hành vi cũ có thể thất bại mà không phải lỗi sản phẩm.

Cần xác định:

1. Yêu cầu mới đã có hiệu lực ở phạm vi nào?
2. Mục tiêu và rủi ro được bảo vệ ra sao?
3. Ca nào cần sửa kỳ vọng, ca nào vẫn giữ?
4. Bằng chứng nào cần tạo lại?
5. Các bản cũ còn được hỗ trợ có baseline khác không?

Không sửa kỳ vọng chỉ vì triển khai hiện tại trả một kết quả khác. Trước hết phải xác nhận thay đổi đó là chủ đích được chấp thuận, không phải hồi quy đang bị hợp thức hóa.

### 13.2. Yêu cầu retire và kiểm thử còn lại

Khi một yêu cầu ngừng hiệu lực có kiểm soát:

- Ngừng chạy những ca chỉ còn kiểm tra hành vi đã thực sự không còn áp dụng trong phạm vi đó.
- Giữ liên kết lịch sử và kết quả của baseline cũ theo chính sách.
- Chuyển các ca phù hợp sang yêu cầu kế nhiệm.
- Giữ kiểm tra cần thiết để ngăn đường cũ bị bật lại ngoài kiểm soát.
- Duy trì ca trên phiên bản hoặc nhóm khách hàng còn áp dụng.

Ví dụ, ngừng reset mật khẩu cục bộ có thể làm một số ca token cũ không còn là nghĩa vụ của baseline mới. Nhưng vẫn cần kiểm tra API cũ không thực hiện reset và cơ chế khôi phục danh tính kế nhiệm đáp ứng yêu cầu.

### 13.3. Loại bỏ trùng lặp có căn cứ

Có thể hợp nhất các ca trùng để giảm thời gian chạy, nhưng cần giữ các chiều có thể làm thay đổi quyết định bảo mật.

Hai ca cùng trả 403 chưa chắc trùng nếu một ca đánh giá quyền ngang và ca kia đánh giá chéo tenant. Hai ca ở tầng hàm và API cũng có thể bảo vệ những lỗi tích hợp khác nhau.

Nên ghi lý do khi bỏ hoặc thay ca, cùng yêu cầu và phạm vi còn được các ca khác hỗ trợ.

## 14. Báo cáo hồi quy có thể dùng để ra quyết định

### 14.1. Phân biệt các trạng thái kết quả

| Trạng thái | Ý nghĩa |
| --- | --- |
| Đạt | Điều kiện thử hợp lệ và kết quả đáp ứng kỳ vọng |
| Không đạt | Có quan sát không đáp ứng yêu cầu hoặc tiêu chí |
| Bị chặn | Không thể hoàn tất đánh giá do điều kiện hoặc phụ thuộc |
| Chưa chạy | Ca thuộc phạm vi nhưng chưa được thực hiện |
| Không áp dụng | Có căn cứ theo baseline và phạm vi, được ghi rõ |

Các nhãn là cách tổ chức báo cáo minh họa. Không tự chuyển lỗi môi trường, timeout hoặc ca bị bỏ qua thành đạt.

### 14.2. Một bản báo cáo ngắn cần gì?

~~~text
Thay đổi:
Tối ưu đường đọc hợp đồng có cache.

Đối tượng đánh giá:
Artifact và cấu hình triển khai đã xác định trong bản ghi chạy.

Yêu cầu liên quan:
SR-TENANT-02, các yêu cầu quyền đối tượng và audit có liên quan.

Phạm vi:
Cache hit/miss, người có quyền, người chéo tenant,
người cùng tenant không có quan hệ quyền, đường tải tệp dùng chung.

Kết quả:
Liệt kê số ca đạt, không đạt, bị chặn và chưa chạy.
Giữ liên kết tới từng ca cùng phiên bản fixture.

Phát hiện:
Request chéo tenant nhận được nội dung khi cache hit,
nếu tình huống đó được quan sát.

Giới hạn:
Nêu cấu hình nhiều nút hoặc đường xuất chưa được đánh giá, nếu có.

Hành động:
Sửa cơ chế, kiểm tra lại và mở rộng theo nguyên nhân;
xác định người chịu trách nhiệm cho phần bằng chứng còn thiếu.
~~~

Mẫu chưa có số liệu thực tế vì đây là nội dung bài học. Trong một báo cáo dùng để quyết định, các giá trị, kết quả và tham chiếu phải được ghi đầy đủ.

### 14.3. Đọc số liệu cùng độ bao phủ

Giả sử 12 ca thuộc phạm vi bắt buộc: 9 đạt, 1 không đạt, 1 bị chặn và 1 chưa chạy. Báo cáo phải giữ đủ bốn nhóm, không gộp thành “đa số đạt”.

Có thể theo dõi:

- Mức bao phủ yêu cầu và các đường quan trọng.
- Các lỗi bảo mật cũ đã có ca hồi quy phù hợp.
- Những lỗi xuất hiện lại dù đã có ca.
- Thời gian phát hiện và xử lý theo nhu cầu của nhóm.
- Số ca không ổn định, bị tách hoặc chưa có người chịu trách nhiệm.
- Thời gian chạy và phần phạm vi thường bị bỏ qua.

Tỷ lệ pass và độ bao phủ mã không tự chứng minh hệ thống không còn lỗ hổng. Chúng phải được đọc cùng tính đúng của oracle, điều kiện thử và các rủi ro chưa được bao phủ.

## 15. Những sai sót làm bộ hồi quy mất giá trị

| Sai sót | Hệ quả | Cách cải thiện |
| --- | --- | --- |
| Chỉ giữ các ca thành công | Không phát hiện đường sử dụng trái quyền | Kết hợp ca dương và âm theo yêu cầu |
| Chỉ chạy lại ca từng lỗi | Bỏ tác động lan sang đường khác | Dùng phân tích nguyên nhân và phụ thuộc |
| Kiểm tra mọi lỗi HTTP đều là đạt | Validation hoặc route lỗi che mất kiểm soát thiếu | Dùng request và fixture hợp lệ, hợp đồng cụ thể |
| Mock bỏ qua cơ chế vừa thay đổi | Bộ thử không chạm phần cần bảo vệ | Có ca tích hợp thực thi kiểm soát liên quan |
| Chỉ đọc phản hồi | Bỏ thay đổi dữ liệu hoặc tác vụ trái phép | Quan sát trạng thái và tác động theo yêu cầu |
| Cache hoặc dữ liệu bị dùng chung giữa ca | Kết quả phụ thuộc thứ tự | Fixture và cơ chế cách ly rõ |
| Retry đến khi xanh | Che vi phạm không ổn định | Giữ thất bại và điều tra nguyên nhân |
| Sửa snapshot theo đầu ra mới ngay lập tức | Hợp thức hóa lộ trường hoặc thay quyền | Đối chiếu yêu cầu trước khi cập nhật kỳ vọng |
| Chọn test chỉ theo file sửa | Bỏ cấu hình và phụ thuộc gián tiếp | Truy vết theo kiểm soát và luồng dữ liệu |
| Không gắn report với artifact | Không biết kết quả áp dụng cho bản nào | Lưu định danh phần mềm, cấu hình và bộ thử |
| Xóa ca vì yêu cầu khó đáp ứng | Mất bằng chứng về rủi ro thật | Xử lý yêu cầu hoặc ngoại lệ đúng quy trình |
| Không bảo trì suite | Ca lỗi thời, chậm và bị bỏ qua | Có người sở hữu, lịch sử thay đổi và rà soát theo tác động |

## 16. Tiêu chí sẵn sàng của bộ hồi quy bảo mật

Đây là kiểm tra về thiết kế và quản lý bằng chứng, không phải chứng nhận hệ thống an toàn tuyệt đối.

- [ ] Các ca trọng yếu liên kết với yêu cầu và phiên bản chính sách.
- [ ] Thay đổi được phân tích về mã, cấu hình, dữ liệu và phụ thuộc.
- [ ] Có ca xác nhận bản sửa và ca hồi quy cho phần chịu ảnh hưởng.
- [ ] Các lỗi cũ có điều kiện tái hiện và kết quả bảo vệ rõ.
- [ ] Oracle xuất phát từ yêu cầu, không chỉ sao chép logic triển khai.
- [ ] Có trường hợp được phép và bị cấm.
- [ ] Dữ liệu, danh tính và trạng thái trước thử phù hợp.
- [ ] Có quan sát tác động nghiệp vụ khi phản hồi chưa đủ.
- [ ] Ca liên quan thời gian và bất đồng bộ có mốc, giới hạn và cách chờ rõ.
- [ ] Cache, chạy song song và fixture không làm lẫn kết quả.
- [ ] Có tầng tích hợp hoặc môi trường phù hợp với kiểm soát đang thay đổi.
- [ ] Phục hồi, migration hoặc nhiều phiên bản được xét khi có tác động.
- [ ] Kết quả thất bại và retry được giữ minh bạch.
- [ ] Ca bị chặn, chưa chạy hoặc tạm tách có người xử lý.
- [ ] Thay đổi yêu cầu và retire có cập nhật truy vết.
- [ ] Report xác định đúng artifact, cấu hình và phạm vi bằng chứng.
- [ ] Các phần chưa đánh giá được trình bày trước khi dựa vào kết quả để ra quyết định.

## 17. Tài liệu tham khảo

- [ISTQB CTFL Syllabus v4.0.1](https://istqb.org/wp-content/uploads/2024/11/ISTQB_CTFL_Syllabus_v4.0.1.pdf): mục 2.2.3 về confirmation testing và regression testing.
- [OWASP SAMM — Requirements-driven Testing](https://owaspsamm.org/model/verification/requirements-driven-testing/): kiểm thử kiểm soát theo yêu cầu và xây dựng bộ hồi quy.
- [OWASP SAMM — Control Verification](https://owaspsamm.org/model/verification/requirements-driven-testing/stream-a/): đánh giá kiểm soát và tự động hóa ca hồi quy cho lỗi đã xử lý.
- [NIST SP 800-218 — SSDF Version 1.1](https://nvlpubs.nist.gov/nistpubs/SpecialPublications/NIST.SP.800-218.pdf): nhóm RV.3 về nguyên nhân, điểm yếu tương tự và giảm tái diễn.
