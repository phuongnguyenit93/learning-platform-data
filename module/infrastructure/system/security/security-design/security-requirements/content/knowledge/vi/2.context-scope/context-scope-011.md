# Out-of-scope và rủi ro còn lại

## 1. Loại khỏi phạm vi không làm mất rủi ro

Một nhóm triển khai chức năng xuất hóa đơn ghi: “Nhà cung cấp danh tính, kho lưu trữ và hệ thống cũ nằm ngoài phạm vi”. Câu này chưa cho biết nhóm đang loại trừ điều gì:

- Không thay đổi mã nguồn của các thành phần đó?
- Không kiểm thử trực tiếp hệ thống của bên cung cấp?
- Không đánh giá các điểm tích hợp?
- Không chịu trách nhiệm theo dõi rủi ro liên quan?

Các cách hiểu dẫn tới nghĩa vụ rất khác nhau. Nhóm có thể không quản lý mã nguồn nhà cung cấp danh tính, nhưng vẫn phải xác định điều kiện chấp nhận danh tính tại API của mình. Nhóm có thể không thay đổi kho lưu trữ, nhưng vẫn phải bảo đảm tệp hóa đơn không được tải bởi người không có quyền.

Trong chương **Bối cảnh và phạm vi**, xác định out-of-scope giúp giới hạn công việc một cách minh bạch. Quản lý rủi ro còn lại giúp giải thích điều gì vẫn có thể xảy ra sau các biện pháp bảo vệ, ai quyết định và khi nào phải xem xét lại.

> **Out-of-scope** mô tả giới hạn của một hoạt động hoặc đối tượng phân tích đã xác định.
>
> **Rủi ro còn lại** mô tả rủi ro vẫn tồn tại sau khi xét các biện pháp xử lý và kiểm soát trong bối cảnh tương ứng.

Hai khái niệm liên quan nhưng không đồng nghĩa. Một hạng mục ngoài phạm vi có thể có rủi ro chưa được đánh giá. Một hạng mục trong phạm vi vẫn có thể còn rủi ro sau khi hoàn tất yêu cầu bảo mật.

Bài học sử dụng ví dụ giả định về dịch vụ hóa đơn nhiều tenant. Các mã, thời hạn và số đo minh họa không phải chính sách mặc định cho mọi dự án.

## 2. Trước hết phải nói rõ phạm vi của việc gì

“Không thuộc phạm vi” chỉ có ý nghĩa khi đi cùng một phạm vi gốc.

| Loại phạm vi | Câu hỏi cần trả lời | Ví dụ phần loại trừ |
| --- | --- | --- |
| Phạm vi hệ thống | Đối tượng phân tích gồm thành phần và luồng nào? | Không phân tích nội bộ hệ thống thanh toán của bên cung cấp |
| Phạm vi thay đổi | Bản phát hành này sửa gì? | Không thay đổi quy trình khôi phục tài khoản hiện hữu |
| Phạm vi đánh giá bảo mật | Đợt đánh giá xem xét tài sản và mối đe dọa nào? | Chưa đánh giá tấn công vật lý tại nơi đặt thiết bị |
| Phạm vi kiểm thử | Phép thử bao phủ môi trường, giao diện và kịch bản nào? | Không thử tải hệ thống của nhà cung cấp trong đợt kiểm thử này |
| Phạm vi trách nhiệm | Bên nào thực hiện và chứng minh nghĩa vụ nào? | Nhóm nền tảng quản lý bản vá hạ tầng; nhóm ứng dụng quản lý chính sách quyền |
| Phạm vi thời gian | Kết luận áp dụng cho phiên bản hoặc giai đoạn nào? | Chức năng ứng dụng di động chưa nằm trong bản phát hành hiện tại |

Một thành phần có thể ngoài phạm vi sửa mã nhưng nằm trong phạm vi đánh giá tác động. Một hệ thống có thể ngoài phạm vi kiểm thử trực tiếp nhưng các yêu cầu đầu vào/đầu ra với nó vẫn nằm trong phạm vi kiểm thử ứng dụng.

### 2.1. Ranh giới quản lý khác ranh giới ảnh hưởng

Ví dụ, nhóm ứng dụng không thể sửa cơ chế phát hành token của nhà cung cấp danh tính. Tuy nhiên, nhóm có thể và cần kiểm soát:

- Nguồn phát hành và đích sử dụng được chấp nhận.
- Cách kiểm tra hiệu lực của thông tin xác thực.
- Cách ánh xạ danh tính sang tenant và quyền nghiệp vụ.
- Hành vi khi thông tin không xác minh được.
- Điều kiện dùng dữ liệu hoặc khóa đã lưu khi phụ thuộc gián đoạn.

Không thể sửa một thành phần không đồng nghĩa không thể giảm tác động từ nó. Cũng không đồng nghĩa nhóm được tự nhận đã kiểm chứng phần bên trong của thành phần đó.

### 2.2. Một phạm vi nên đủ rõ để người khác diễn giải giống nhau

Một mô tả hữu ích cần nêu:

- Mục tiêu của hoạt động.
- Chức năng, tài sản, luồng dữ liệu và môi trường được xét.
- Phiên bản hoặc thời điểm áp dụng.
- Chủ thể và loại đe dọa được xét.
- Phụ thuộc và giả định có ảnh hưởng.
- Phần bị loại trừ cùng lý do.
- Những nghĩa vụ tại ranh giới vẫn phải thực hiện.

“Không làm bảo mật cho bên thứ ba” không đáp ứng các thông tin đó. “Không kiểm tra mã nội bộ của nhà cung cấp lưu trữ; vẫn kiểm tra danh tính máy, quyền truy cập tệp và điều kiện tải tại ứng dụng” cụ thể hơn nhiều.

## 3. Các khái niệm dễ bị gộp nhầm

| Khái niệm | Ý nghĩa | Không nên suy ra |
| --- | --- | --- |
| Out-of-scope | Một phần công việc hoặc đối tượng được loại khỏi phạm vi đã nêu | Không có rủi ro hoặc không cần theo dõi ảnh hưởng |
| Giả định | Điều đang được coi là đúng để lập luận hoặc thiết kế | Đã có bằng chứng xác nhận |
| Hạn chế đánh giá | Giới hạn của dữ liệu, thời gian, quyền truy cập hoặc phương pháp | Phần chưa xem xét chắc chắn đạt yêu cầu |
| Yêu cầu chưa đáp ứng | Nghĩa vụ đã đặt ra nhưng hệ thống chưa đáp ứng hoặc chưa đủ bằng chứng | Tự trở thành ngoài phạm vi |
| Hoãn xử lý | Quyết định chưa thực hiện công việc trong giai đoạn hiện tại | Rủi ro đã được chấp nhận đúng thẩm quyền |
| Rủi ro còn lại | Rủi ro tồn tại sau khi xét các biện pháp kiểm soát và xử lý | Tự động là rủi ro được chấp nhận |
| Chấp nhận rủi ro | Quyết định có thẩm quyền duy trì rủi ro trong điều kiện đã nêu | Hệ thống đã đáp ứng yêu cầu ban đầu |
| Ngoại lệ | Sự lệch khỏi một nghĩa vụ hoặc chính sách được quản lý riêng | Miễn trừ vô thời hạn cho mọi trường hợp |

### 3.1. Rủi ro còn lại khác rủi ro chưa biết rõ

Giả sử tệp xuất đã được mã hóa và kiểm tra quyền tải, nhưng người dùng hợp lệ vẫn có thể chụp màn hình hoặc chia sẻ dữ liệu sau khi tải. Đó có thể là một phần rủi ro còn lại cần mô tả theo mô hình đe dọa.

Ngược lại, nếu chưa biết bản sao lưu có mã hóa hay không, không nên ghi “rủi ro còn lại thấp”. Trước hết cần ghi nhận thông tin thiếu, giả định và tác động nếu giả định sai.

Có thể đánh giá:

- **Rủi ro trước xử lý:** bối cảnh trước các biện pháp được xét.
- **Rủi ro hiện tại:** bối cảnh với các biện pháp thực sự đang có.
- **Rủi ro dự kiến sau xử lý:** bối cảnh giả định các biện pháp dự kiến đã được thực hiện và hoạt động.

Rủi ro dự kiến chưa phải bằng chứng rằng mức rủi ro thực tế đã giảm. Một hạng mục ghi “sẽ thêm kiểm tra quyền” không cho phép báo rằng lỗi truy cập sai quyền đã được khắc phục.

### 3.2. Chấp nhận rủi ro không làm thay đổi sự thật kỹ thuật

Nếu một yêu cầu quy định quyền bị thu hồi hết hiệu lực trong tối đa 60 giây, nhưng thiết kế thực tế có thể chấp nhận quyền cũ trong 5 phút, yêu cầu vẫn chưa được đáp ứng.

Người có thẩm quyền có thể quyết định một ngoại lệ tạm thời trong phạm vi cho phép. Báo cáo cần giữ cả hai thông tin:

1. Nghĩa vụ kỹ thuật nào chưa đạt.
2. Quyết định quản lý nào cho phép tiếp tục trong điều kiện nào.

Không sửa kết quả kiểm thử thành đạt chỉ vì đã có quyết định chấp nhận rủi ro.

## 4. Bối cảnh xuyên suốt: xuất hóa đơn nhiều tenant

Mỗi tenant là một tổ chức khách hàng có dữ liệu và quyền riêng. Một bản phát hành thêm chức năng:

1. Người dùng yêu cầu xuất hóa đơn.
2. Máy chủ kiểm tra quyền và tạo công việc xuất.
3. Worker đọc dữ liệu để sinh tệp.
4. Tệp được lưu trong kho đối tượng.
5. Người dùng tải tệp qua một đường truy cập được kiểm soát.
6. Sự kiện yêu cầu, tạo và tải tệp được ghi nhận theo chính sách kiểm toán.

Tài sản cần bảo vệ gồm dữ liệu hóa đơn, thông tin cá nhân trên hóa đơn, quyền truy cập tenant, tệp xuất, thông tin xác thực và dấu vết kiểm toán.

Những tình huống đe dọa liên quan:

| Mã | Tình huống | Hậu quả |
| --- | --- | --- |
| R-EXP-01 | Người dùng tenant A yêu cầu hoặc tải tệp của tenant B | Rò rỉ dữ liệu liên tổ chức |
| R-EXP-02 | Liên kết tải bị chia sẻ hoặc xuất hiện trong log | Người khác có thể lấy được dữ liệu tùy cơ chế tải |
| R-EXP-03 | Quyền bị thu hồi sau khi tạo công việc nhưng trước khi tải | Chủ thể tiếp tục truy cập bằng trạng thái quyền cũ |
| R-EXP-04 | Tệp hoặc bản sao không được xóa theo chính sách | Dữ liệu tồn tại quá thời gian cần thiết |
| R-EXP-05 | Dịch vụ danh tính hoặc kho đối tượng gián đoạn | Không thể phục vụ hoặc xử lý lỗi làm yếu kiểm soát |
| R-EXP-06 | Phục hồi từ dữ liệu cũ làm sống lại tệp hay quyền truy cập | Mở lại truy cập không còn hợp lệ |

Không phải mọi biện pháp cho các tình huống trên đều nằm trong một bản phát hành. Tuy nhiên, nhóm cần mô tả rõ phần nào được xử lý, phần nào đã có kiểm soát, phần nào còn thiếu và ai quyết định.

## 5. Ghi một hạng mục out-of-scope như thế nào?

Một dòng “không xử lý hệ thống cũ” quá rộng. Nên ghi thành một quyết định có cấu trúc.

| Trường | Nội dung |
| --- | --- |
| Mã hạng mục | Định danh dùng để liên kết |
| Phạm vi gốc | Bản phát hành, đợt đánh giá hay phép kiểm thử nào |
| Phần loại trừ | Thành phần, luồng, chức năng hoặc loại hoạt động cụ thể |
| Lý do | Giới hạn trách nhiệm, mục tiêu giai đoạn, điều kiện tiếp cận hoặc quyết định nghiệp vụ |
| Phần vẫn nằm trong phạm vi | Tích hợp, dữ liệu, quyền và hành vi lỗi cần kiểm soát |
| Phụ thuộc và giả định | Điều gì phải đúng để việc loại trừ không làm sai lập luận |
| Rủi ro liên quan | Tình huống đe dọa và tác động cần theo dõi |
| Chủ sở hữu | Người quản lý hạng mục và người xử lý phần liên quan |
| Bằng chứng | Căn cứ xác định kiểm soát hiện hữu hoặc phần đã được đánh giá |
| Điều kiện xem xét lại | Thay đổi, sự cố, thời hạn hoặc phát hiện làm quyết định không còn phù hợp |

### Ví dụ OOS-01: không đánh giá nội bộ nhà cung cấp lưu trữ

```text
Mã: OOS-01
Phạm vi gốc: Đánh giá chức năng xuất hóa đơn của bản phát hành E1

Loại trừ:
  Không kiểm tra mã nguồn và hạ tầng nội bộ do nhà cung cấp
  kho đối tượng vận hành.

Lý do:
  Không thuộc quyền kiểm soát và quyền kiểm thử của nhóm ứng dụng.

Vẫn trong phạm vi:
  - Quyền của danh tính máy dùng để đọc/ghi tệp.
  - Cách ly đường dẫn và đối tượng giữa các tenant.
  - Điều kiện ứng dụng cho phép tải tệp.
  - Dữ liệu gửi tới kho và chính sách vòng đời tệp.
  - Hành vi khi lưu, đọc hoặc xóa thất bại.
  - Phụ thuộc của việc phục hồi vào kho và khóa mã hóa.

Giả định:
  Năng lực bảo vệ và nghĩa vụ dữ liệu của dịch vụ phù hợp
  với phạm vi sử dụng đã được chấp thuận.

Cần xác minh:
  Bằng chứng và cam kết liên quan tới phần nhà cung cấp chịu trách nhiệm.

Xem xét lại khi:
  Đổi nhà cung cấp, thay quyền truy cập, thay loại dữ liệu
  hoặc có sự cố ảnh hưởng tới giả định.
```

Đây là giới hạn hoạt động đánh giá trực tiếp, không phải tuyên bố rằng nhà cung cấp không có rủi ro hoặc ứng dụng không chịu trách nhiệm với cấu hình tích hợp.

### Ví dụ OOS-02: không sửa quy trình khôi phục tài khoản

Quy trình khôi phục tài khoản có thể ngoài phạm vi thay đổi của E1. Tuy nhiên, chức năng xuất hóa đơn vẫn dựa vào danh tính được cấp sau quy trình đó.

Cần ghi rủi ro chiếm tài khoản có thể dẫn tới tải dữ liệu. Nếu đã biết một điểm yếu nghiêm trọng ở quy trình khôi phục, không thể chỉ xếp nó vào ngoài phạm vi rồi bỏ khỏi đánh giá phát hành. Cần người có trách nhiệm xác định tác động, xử lý hoặc quyết định rủi ro theo thẩm quyền.

“Không sửa trong E1” và “không xem xét tác động tới E1” là hai quyết định khác nhau.

## 6. Khi nào việc loại trừ có căn cứ?

Một hạng mục có thể được loại khỏi một hoạt động khi ranh giới rõ, lý do phù hợp và phần ảnh hưởng được quản lý. Ví dụ:

- Ứng dụng di động chưa được phát hành, trong khi đợt đánh giá hiện tại dành cho API và giao diện web đang triển khai.
- Nội bộ nhà cung cấp không được kiểm thử trực tiếp, nhưng có nghĩa vụ tại giao diện và phương án đánh giá phần cung cấp.
- Một chức năng không thay đổi trong bản phát hành, nhưng vẫn được xem xét nếu thay đổi mới tác động tới quyền hoặc dữ liệu của nó.
- Một loại tấn công thuộc phạm vi đánh giá khác với người chịu trách nhiệm đã được xác định.

Ngược lại, các lý do sau chưa đủ để bỏ nghĩa vụ:

- “Chưa có thời gian.”
- “Thành phần này đã tồn tại lâu.”
- “Chưa từng có sự cố.”
- “Nhà cung cấp lớn nên chắc an toàn.”
- “Kiểm thử khó nên không tính.”
- “Đội khác quản lý nên không cần đầu mối.”

Thiếu thời gian hoặc khó kiểm thử có thể là một hạn chế thực tế. Khi đó cần ghi hạn chế, mức thiếu bằng chứng và tác động, thay vì đổi tên thành không có rủi ro.

### Câu hỏi trước khi chốt loại trừ

1. Loại khỏi hoạt động nào?
2. Có luồng dữ liệu, quyền hoặc phụ thuộc nào nối phần đó với phạm vi đang làm không?
3. Kết luận bảo mật hiện tại có dựa vào giả định về phần đó không?
4. Ai quản lý nghĩa vụ nằm bên kia ranh giới?
5. Rủi ro đã biết có được ghi nhận và quyết định riêng chưa?
6. Khi giả định sai hoặc bối cảnh thay đổi, điều gì kích hoạt xem xét lại?

Một yêu cầu áp dụng từ nguồn nghĩa vụ có thẩm quyền không thể bị một nhóm tự xóa bằng nhãn out-of-scope. Cần xác định đúng cơ quan hoặc vai trò có quyền thay đổi nghĩa vụ đó.

## 7. Nhận diện rủi ro còn lại sau xử lý

Một cách mô tả rủi ro:

> Trong **bối cảnh**, **tác nhân hoặc sự kiện** có thể khai thác **điểm yếu hay điều kiện**, gây **tác động lên tài sản**. Các kiểm soát hiện hữu giảm phần nào của rủi ro, và phần nào vẫn còn?

Ví dụ:

> Sau khi hệ thống kiểm tra quyền tại lúc tải và không ghi liên kết tải vào log, người dùng được cấp quyền vẫn có thể lưu bản sao tệp trên thiết bị và chia sẻ ra ngoài. Hệ thống giảm truy cập không được cấp quyền tại máy chủ, nhưng chưa kiểm soát hoàn toàn việc sử dụng bản sao sau khi đã tải hợp lệ.

Điều này không có nghĩa phải giải quyết toàn bộ bằng một công nghệ duy nhất. Nó làm rõ giới hạn của biện pháp và hỗ trợ quyết định về loại dữ liệu, quyền xuất, trách nhiệm người dùng hoặc điều kiện sử dụng.

### 7.1. Tách các loại rủi ro và khoảng trống

| Tình huống | Cách ghi nhận phù hợp |
| --- | --- |
| Control đã triển khai và kiểm chứng nhưng vẫn còn một đường gây tổn thất | Rủi ro còn lại với căn cứ và giới hạn bằng chứng |
| Control mới có trong kế hoạch | Rủi ro hiện tại và mức dự kiến sau xử lý phải ghi riêng |
| Chưa xác định control có hoạt động không | Khoảng chưa biết hoặc thiếu bằng chứng; cần đánh giá |
| Yêu cầu bắt buộc chưa thực hiện | Khoảng không đáp ứng, liên kết tới rủi ro và quyết định xử lý |
| Phần chưa thuộc đợt đánh giá | Hạn chế hoặc loại trừ; không tự gán mức rủi ro thấp |
| Rủi ro được người có thẩm quyền chấp nhận | Rủi ro có quyết định chấp nhận trong điều kiện xác định |

Không cần buộc mọi trường hợp vào cùng một nhãn “residual risk”. Cần giữ trạng thái đủ rõ để người quyết định hiểu mức độ đã biết.

### 7.2. Đánh giá khả năng và tác động theo bối cảnh

Cần cân nhắc:

- Mức nhạy cảm và quy mô dữ liệu.
- Chủ thể nào có thể gây ra tình huống.
- Điều kiện tiên quyết và đường tấn công.
- Phạm vi tenant hoặc chức năng bị ảnh hưởng.
- Khả năng phát hiện, giới hạn tác động và phục hồi.
- Hiệu quả kiểm soát cùng bằng chứng hiện có.
- Độ không chắc chắn và các giả định chưa xác minh.

Nếu tổ chức dùng thang mức hoặc mô hình chấm điểm, phải dùng định nghĩa thống nhất. Không nhân các nhãn mức tùy ý rồi coi kết quả là một ước lượng chính xác.

Một mức “thấp” cần có lý do. Độ không chắc chắn lớn cũng cần được đưa tới người quyết định, không giấu trong một con số duy nhất.

### 7.3. Không suy ra rủi ro bằng không từ kiểm thử đạt

Một bộ kiểm thử chứng minh các tình huống đã thử đáp ứng tiêu chí trong điều kiện đã nêu. Nó không chứng minh không thể tồn tại tình huống ngoài tập thử, lỗi trong phụ thuộc hoặc thay đổi cấu hình sau đó.

Rủi ro còn lại cần được giải thích bằng mô hình, kiểm soát và giới hạn bằng chứng. Không chỉ ghi “test pass nên không còn rủi ro”.

## 8. Chọn cách xử lý và quyết định phần còn lại

Sau khi hiểu rủi ro, có thể lựa chọn một hoặc kết hợp nhiều hướng:

| Hướng xử lý | Ý nghĩa | Ví dụ trong chức năng xuất hóa đơn |
| --- | --- | --- |
| Tránh | Bỏ hoặc thay đổi hoạt động tạo ra rủi ro | Không cung cấp loại xuất chứa dữ liệu chưa được phép đưa ra ngoài |
| Giảm | Giảm khả năng xảy ra hoặc tác động | Giới hạn trường xuất, kiểm tra quyền tại lúc tải, bảo vệ tệp và log |
| Chia sẻ hoặc chuyển giao một phần | Phân bổ một phần xử lý hay tổn thất qua thỏa thuận phù hợp | Dùng dịch vụ chuyên trách với trách nhiệm dữ liệu và hỗ trợ được xác nhận |
| Chấp nhận | Duy trì rủi ro trong phạm vi và điều kiện được quyết định | Chấp nhận giới hạn kiểm soát bản sao sau khi người dùng hợp lệ tải, kèm điều kiện cụ thể |

Chuyển một hoạt động cho nhà cung cấp không chuyển hết trách nhiệm và không làm mọi tác động biến mất. Tổ chức vẫn cần quản lý cách sử dụng dịch vụ, dữ liệu gửi đi và phần rủi ro mình giữ lại.

### 8.1. Ai có thể chấp nhận rủi ro?

Vai trò có thẩm quyền tùy quy định của tổ chức, mức rủi ro và loại tài sản. Có thể cần chủ sở hữu nghiệp vụ, chủ sở hữu dữ liệu, bộ phận an toàn thông tin hoặc cấp quản lý phù hợp.

Nhà phát triển có thể phân tích, đề xuất và cung cấp bằng chứng. Việc tự đánh dấu “accepted” trong một công việc không tự tạo thành quyết định hợp lệ.

Người quyết định cần được cung cấp:

- Tình huống và tác động có thể xảy ra.
- Phạm vi dữ liệu, chức năng, tenant và thời gian.
- Kiểm soát hiện hữu và bằng chứng.
- Khoảng chưa biết.
- Các phương án khác cùng chi phí và giới hạn.
- Yêu cầu hoặc chính sách nào chưa được đáp ứng, nếu có.
- Điều kiện duy trì và tác nhân kích hoạt xem xét lại.

Quyền chấp nhận rủi ro cũng có giới hạn. Một vai trò không được tự miễn nghĩa vụ ngoài thẩm quyền của mình. Các nguồn nghĩa vụ áp dụng phải được xác định trước khi kết luận có thể cấp ngoại lệ.

### 8.2. Quyết định cần có phạm vi và thời hạn

Một quyết định tốt cần nêu:

```text
Chấp nhận rủi ro nào?
Áp dụng cho phiên bản, dữ liệu và nhóm sử dụng nào?
Trong thời gian nào?
Dựa vào bằng chứng và giả định nào?
Kiểm soát nào bắt buộc tiếp tục hoạt động?
Ai theo dõi và ai có quyền quyết định?
Điều gì khiến quyết định phải được xem xét lại sớm?
Khi hết hạn, phải sửa, đánh giá lại hay dừng phạm vi nào?
```

Không nên dùng “chấp nhận cho đến khi có thời gian xử lý” làm một thời hạn có ý nghĩa. Một quyết định hết hạn không tự gia hạn vì công việc khắc phục chưa hoàn tất.

### 8.3. Chấp nhận rủi ro khác nghiệm thu requirement

Một yêu cầu có thể đạt nhưng vẫn còn rủi ro trong mô hình đe dọa rộng hơn. Ngược lại, có thể có quyết định ngoại lệ cho một yêu cầu chưa đạt.

Vì vậy, cần theo dõi riêng:

- Trạng thái đáp ứng yêu cầu.
- Mức rủi ro hiện tại.
- Trạng thái xử lý rủi ro.
- Trạng thái và thời hạn quyết định chấp nhận hoặc ngoại lệ.

Gộp chúng thành một ô “xong” sẽ làm mất thông tin quan trọng cho người vận hành và người phê duyệt phát hành.

## 9. Hồ sơ rủi ro còn lại cần ghi gì?

| Trường | Mục đích |
| --- | --- |
| Mã rủi ro | Liên kết nhất quán với yêu cầu và quyết định |
| Mô tả tình huống | Nêu chủ thể/sự kiện, điều kiện, tài sản và tác động |
| Phạm vi áp dụng | Phiên bản, chức năng, dữ liệu, tenant hoặc môi trường |
| Liên kết loại trừ | Chỉ ra hạng mục out-of-scope liên quan, nếu có |
| Kiểm soát hiện hữu | Mô tả biện pháp đã thực hiện, không lẫn với kế hoạch |
| Bằng chứng | Kết quả kiểm thử, rà soát hoặc diễn tập có phạm vi rõ |
| Phần rủi ro còn lại | Giới hạn mà kiểm soát hiện hữu chưa loại bỏ |
| Đánh giá và độ chắc chắn | Lý do về khả năng, tác động và thông tin thiếu |
| Yêu cầu liên quan | Nghĩa vụ đạt, chưa đạt hoặc chưa đủ bằng chứng |
| Phương án xử lý | Giảm, tránh, chia sẻ hoặc đề xuất chấp nhận |
| Chủ sở hữu rủi ro | Người theo dõi và điều phối xử lý |
| Người quyết định | Vai trò có thẩm quyền cùng tham chiếu quyết định |
| Điều kiện và thời hạn | Các ràng buộc phải duy trì và mốc xem xét |
| Tác nhân thay đổi | Sự cố hoặc thay đổi khiến đánh giá phải mở lại |

Hồ sơ rủi ro và danh sách out-of-scope nên liên kết được nhưng không cần trộn thành một bảng duy nhất. Một loại trừ có thể liên quan nhiều rủi ro; một rủi ro có thể đi qua nhiều thành phần cả trong và ngoài phạm vi.

### Ví dụ RR-EXP-01: dữ liệu đã được tải hợp lệ bị chia sẻ tiếp

```text
Mã: RR-EXP-01

Tình huống:
  Người dùng có quyền xuất tải tệp hợp lệ, sau đó chia sẻ bản sao
  cho người không được phép nhận.

Phạm vi:
  Chức năng xuất của E1 và tập trường dữ liệu đã được phê duyệt.
  Không áp dụng cho loại dữ liệu chưa được phép xuất.

Kiểm soát hiện hữu:
  - Quyền xuất và quyền tải theo tenant, hành động và đối tượng.
  - Giới hạn trường dữ liệu.
  - Sự kiện kiểm toán yêu cầu/tải theo chính sách.
  - Vòng đời tệp phía máy chủ được quản lý.

Bằng chứng cần có:
  Kiểm thử quyền, trường xuất, sự kiện và vòng đời tệp
  đối với phiên bản E1.

Phần còn lại:
  Xóa tệp ở máy chủ không thu hồi được mọi bản sao đã tải.
  Kiểm toán không tự ngăn được chia sẻ sau khi tải hợp lệ.

Trạng thái:
  Đề xuất đánh giá và quyết định; chưa tự coi là đã chấp nhận.

Điều kiện cần xem xét:
  Loại dữ liệu, nhóm người dùng, quy định sử dụng,
  cơ chế phát hiện và xử lý vi phạm phù hợp bối cảnh.

Xem xét lại:
  Khi thêm trường nhạy cảm, mở quyền xuất cho nhóm mới
  hoặc xuất hiện bằng chứng lạm dụng.
```

Ví dụ không mặc định gán mức thấp hoặc chấp nhận. Mức rủi ro phụ thuộc loại dữ liệu và hậu quả thực tế.

## 10. Ví dụ phân biệt ba tình huống dễ nhầm

### 10.1. Không đánh giá nội bộ nhà cung cấp

Nhóm không kiểm tra mã bên trong kho đối tượng. Đây là một phần ngoài phạm vi của hoạt động đánh giá trực tiếp.

Nhóm vẫn phải xem xét quyền máy, chính sách tải và dữ liệu lưu. Nếu chưa có thông tin cần thiết về phần cung cấp, ghi nhận hạn chế và giả định cần xác minh. Không thể kết luận “rủi ro còn lại thấp” chỉ từ việc đã đặt phần đó ngoài phạm vi.

**Kết luận:** một giới hạn đánh giá kèm trách nhiệm tại ranh giới; mức rủi ro còn phải có căn cứ.

### 10.2. Liên kết tải còn dùng được sau khi thu hồi quyền

Giả sử yêu cầu đặt ra:

> Sau tối đa 60 giây kể từ khi thu hồi quyền được ghi nhận thành công, chủ thể không được tải tệp dựa trên quyền đã bị thu hồi.

Thiết kế hiện tại lại phát hành liên kết trực tiếp có hiệu lực 10 phút và không kiểm tra lại quyền lúc tải. Nếu liên kết hoạt động như một thông tin mang quyền truy cập, người giữ liên kết có thể tiếp tục tải trong thời hạn đó.

Cần xác minh cơ chế thực tế, nhưng nếu hành vi này xảy ra thì yêu cầu 60 giây chưa được đáp ứng.

Nhóm có thể cân nhắc kiểm tra quyền tại điểm tải, cơ chế thu hồi phù hợp hoặc thiết kế khác. Chỉ đổi thời hạn liên kết thành 60 giây cũng chưa tự chứng minh toàn bộ nghĩa vụ đã đạt nếu công việc cũ vẫn có thể tạo liên kết mới bằng quyền cũ.

Nếu đề xuất tạm thời tiếp tục sử dụng thiết kế, cần hồ sơ không đáp ứng, đánh giá rủi ro và quyết định ngoại lệ đúng thẩm quyền. Không chỉ đổi nhãn thành “ngoài phạm vi E1”.

**Kết luận:** khoảng không đáp ứng cụ thể; trạng thái yêu cầu và quyết định rủi ro phải tách riêng.

### 10.3. Người được cấp quyền sao chép dữ liệu đã tải

Giả sử yêu cầu trong phạm vi là kiểm soát truy cập máy chủ, trường xuất và vòng đời tệp phía máy chủ. Các yêu cầu đó đã có bằng chứng đáp ứng trong điều kiện đã định.

Người hợp lệ vẫn có thể lưu và chia sẻ dữ liệu sau khi tải. Đây là một rủi ro cần đánh giá theo giới hạn biện pháp hiện hữu. Nếu tổ chức quyết định chấp nhận trong một phạm vi xác định, cần lưu quyết định và điều kiện duy trì.

Nếu có thêm nghĩa vụ áp dụng về kiểm soát sử dụng sau tải, phải đưa nghĩa vụ đó vào đánh giá. Không được dùng ví dụ này để mặc định mọi hệ thống đều được phép bỏ qua.

**Kết luận:** có thể là rủi ro còn lại dù yêu cầu trong phạm vi đã đạt; việc chấp nhận vẫn cần quyết định riêng.

## 11. Chuyển phần ảnh hưởng thành yêu cầu và bằng chứng

Nhãn out-of-scope cần đi cùng nghĩa vụ tại ranh giới. Bảng dưới minh họa cách nối bối cảnh với đặc tả.

| Phần không trực tiếp kiểm soát hoặc thay đổi | Yêu cầu ở phần hệ thống chịu trách nhiệm | Bằng chứng phù hợp |
| --- | --- | --- |
| Nhà cung cấp danh tính | Chỉ chấp nhận danh tính đúng nguồn, đúng đích và còn hiệu lực theo giao thức đã chọn | Thử đúng/sai nguồn, sai đích, hết hạn và điều kiện lỗi |
| Kho lưu trữ do nhóm khác vận hành | Không cho tải tệp khi chủ thể không có quyền với tenant và đối tượng | Kiểm thử đúng quyền, sai tenant, sai tệp và đường tải trực tiếp liên quan |
| Thư viện thu thập lỗi | Không gửi mật khẩu, token và dữ liệu bị cấm tới nơi nhận lỗi | Kích hoạt lỗi bằng dữ liệu thử chứa bí mật rồi kiểm tra đầu ra thực tế |
| Quy trình phục hồi do nhóm nền tảng thực hiện | Chỉ mở lại chức năng nhạy cảm khi dữ liệu và trạng thái quyền đáp ứng điều kiện phục hồi | Diễn tập với khóa, danh tính và quyền thực tế trong phạm vi đã định |
| Cơ chế gửi thông báo bên ngoài | Chỉ gửi trường và người nhận được phép; hành vi lỗi không làm lộ dữ liệu | Thử sai người nhận, lỗi gửi, gửi lại và quan sát dữ liệu lưu trong hàng đợi/log |

### 11.1. Viết rõ kết quả quan sát được

“Tin cậy hệ thống danh tính” là một giả định quá rộng. “Từ chối token sai đích sử dụng và không tạo phiên ứng dụng” là nghĩa vụ cụ thể hơn.

“Kho lưu trữ bảo mật” cũng chưa đủ. Cần biết ai được đọc tệp, bằng đường nào, trong thời hạn nào và kết quả khi quyền không hợp lệ.

Yêu cầu có thể cần định lượng nếu mức rủi ro phụ thuộc vào thời gian hoặc lượng dữ liệu, chẳng hạn thời hạn thu hồi, độ trễ sự kiện kiểm toán hoặc mục tiêu phục hồi. Không tự đặt số chỉ để làm tài liệu có vẻ chính xác.

### 11.2. Chọn bằng chứng đúng loại

- Kiểm thử quyền cần quan sát cả phản hồi và tác động dữ liệu.
- Kiểm tra dữ liệu log cần xem các đầu ra thực tế trong phạm vi, gồm lỗi và thuộc tính tự động.
- Yêu cầu về độ trễ cần mốc đo, tải, nguồn thời gian và cách xử lý mẫu lỗi.
- Yêu cầu phục hồi cần dữ liệu khôi phục được và điều kiện mở lại nghiệp vụ.
- Phần không thể kiểm thử trực tiếp cần ghi bằng chứng thay thế cùng giới hạn của nó.

Tài liệu nhà cung cấp có thể hỗ trợ một lập luận, nhưng không thay thế kiểm thử cấu hình tích hợp của ứng dụng. Không có quyền đánh giá nội bộ bên cung cấp cũng không cho phép báo đã kiểm thử phần đó.

## 12. Báo cáo phạm vi và rủi ro trước phát hành

Một báo cáo có ích cần giúp người nhận phân biệt điều đã làm, điều chưa biết và điều đã được quyết định.

Có thể tổ chức thành các nhóm thông tin song song:

| Nội dung | Cần thể hiện |
| --- | --- |
| Phạm vi | Phiên bản, chức năng, môi trường, tài sản và luồng được xét |
| Loại trừ | Phần không làm, lý do và nghĩa vụ còn giữ tại ranh giới |
| Yêu cầu | Đạt, không đạt, chưa đủ bằng chứng hoặc không áp dụng có căn cứ |
| Hạn chế đánh giá | Phép thử chưa thực hiện, dữ liệu thiếu, giả định chưa xác minh |
| Rủi ro | Mức hiện tại, lý do, phần còn lại và chủ sở hữu |
| Quyết định | Xử lý, chấp nhận, ngoại lệ, điều kiện và thời hạn |
| Việc tiếp theo | Hạng mục khắc phục, người chịu trách nhiệm và tác nhân xem xét lại |

### 12.1. Diễn đạt kết luận trong đúng phạm vi

Một kết luận phù hợp có thể là:

> Đã kiểm chứng các tiêu chí phân quyền của luồng tạo và tải tệp đối với phiên bản E1 trong môi trường thử được mô tả. Không đánh giá mã nội bộ của nhà cung cấp kho đối tượng. Phần tích hợp và cấu hình truy cập thuộc phạm vi đã được kiểm tra. Rủi ro sử dụng dữ liệu sau khi tải hợp lệ đang chờ quyết định riêng.

Không nên thay toàn bộ nội dung này bằng “hệ thống an toàn” hoặc “đạt mọi yêu cầu” nếu còn khoảng trống.

### 12.2. “Không áp dụng” cũng phải có lý do

Một yêu cầu có thể không áp dụng nếu tiền đề của nó thực sự không tồn tại trong phạm vi. Ví dụ, yêu cầu dành riêng cho chức năng thanh toán không áp dụng cho một hệ thống không có luồng hoặc phụ thuộc thanh toán.

Tuy nhiên, không được đánh dấu không áp dụng chỉ vì chưa triển khai control. Nếu hệ thống có tệp chứa dữ liệu nhạy cảm thì yêu cầu bảo vệ tệp không biến mất khi nhóm chưa kịp thêm phân quyền.

Cần giữ căn cứ để người khác kiểm tra lại khi chức năng thay đổi.

### 12.3. Phát hành có điều kiện cần điều kiện quan sát được

Nếu một quyết định cho phép phát hành trong phạm vi giới hạn, điều kiện phải có thể thực hiện và theo dõi, chẳng hạn:

- Chỉ áp dụng cho tập trường dữ liệu đã được phê duyệt.
- Chỉ bật cho nhóm người dùng có quyền đã được xác định.
- Có cơ chế tắt chức năng và trách nhiệm xử lý sự kiện.
- Có thời hạn đánh giá lại và hạng mục xử lý rõ.
- Các kiểm soát được dùng làm căn cứ quyết định tiếp tục hoạt động.

Đây là ví dụ về cấu trúc điều kiện, không tự chứng minh một phương án phát hành là chấp nhận được. Tính phù hợp phải được quyết định theo rủi ro và thẩm quyền thực tế.

## 13. Khi nào phải mở lại đánh giá?

Phạm vi và rủi ro không cố định theo thời gian. Cần xem xét lại khi:

- Thêm dữ liệu nhạy cảm hoặc tăng quy mô dữ liệu xuất.
- Mở chức năng cho tenant, vai trò hoặc kênh truy cập mới.
- Thay đổi nhà cung cấp, quyền máy, cơ chế xác thực hoặc lưu trữ.
- Thay đổi thời hạn tệp, phiên, liên kết hoặc cache quyền.
- Có sự cố, phát hiện mới hoặc bằng chứng control không hoạt động.
- Khôi phục từ bản sao lưu làm thay đổi trạng thái quyền hay dữ liệu.
- Hết hạn quyết định chấp nhận hoặc ngoại lệ.
- Giả định nền không còn đúng hoặc chưa thể xác minh như kế hoạch.

### Ví dụ: thay đổi loại dữ liệu

Ban đầu tệp chỉ chứa mã và tổng tiền hóa đơn. Sau đó nhóm thêm thông tin tài khoản thanh toán.

Quyết định chấp nhận rủi ro cho tập trường cũ không tự áp dụng cho tập mới. Tác động khi chia sẻ, yêu cầu dữ liệu, logging và quyền xuất có thể thay đổi. Cần cập nhật phạm vi, mô hình đe dọa, yêu cầu và quyết định liên quan.

### Ví dụ: control làm căn cứ quyết định bị tắt

Nếu rủi ro được chấp nhận với điều kiện sự kiện tải được ghi và đối soát, việc tắt logging hoặc mất đối soát làm điều kiện không còn được duy trì.

Không đợi đến kỳ rà soát mới ghi nhận. Cần xử lý theo cơ chế giám sát và quyết định đã xác định, bao gồm xem xét giới hạn hoặc dừng phần chức năng liên quan khi thích hợp.

## 14. Những lỗi thường gặp

| Cách làm | Vấn đề | Cách sửa |
| --- | --- | --- |
| “Bên thứ ba ngoài phạm vi” | Không rõ hoạt động nào bị loại, nghĩa vụ tích hợp bị bỏ trống | Ghi phần loại trừ và phần vẫn phải kiểm soát |
| “Không thay mã nên không cần đánh giá” | Thay đổi mới có thể ảnh hưởng tới dữ liệu và quyền cũ | Đánh giá tác động theo luồng và phụ thuộc |
| “Chưa test nên coi là không áp dụng” | Biến thiếu bằng chứng thành loại trừ không có căn cứ | Ghi hạn chế và yêu cầu chưa được chứng minh |
| “Sẽ thêm control nên rủi ro đã giảm” | Gộp mức dự kiến với mức hiện tại | Tách kế hoạch, triển khai và bằng chứng |
| “Risk accepted nên requirement pass” | Trộn quyết định quản trị với kết quả kỹ thuật | Giữ hai trạng thái độc lập và liên kết |
| “Dùng dịch vụ thuê ngoài là chuyển hết rủi ro” | Bỏ phần cấu hình, dữ liệu và tổn thất còn giữ lại | Phân bổ trách nhiệm theo từng nghĩa vụ |
| “Ngoại lệ đến khi sửa xong” | Không có mốc đánh giá lại có thể quản lý | Đặt thời hạn và hành động khi hết hạn |
| “Test pass nên không còn rủi ro” | Kết luận vượt quá phạm vi bằng chứng | Nêu giới hạn và rủi ro còn lại |
| “Chưa xảy ra sự cố nên mức thấp” | Thiếu bằng chứng về khả năng và tác động | Đánh giá theo bối cảnh, kiểm soát và mức không chắc chắn |

## 15. Bài tập tự kiểm tra

### Bài 1: Phân biệt loại trừ và khoảng không đáp ứng

Một bản phát hành không thay đổi quy trình khôi phục tài khoản. Nhóm phát hiện quy trình này có thể cho phép chiếm tài khoản đang có quyền xuất dữ liệu.

Có thể chỉ ghi “ngoài phạm vi” rồi kết thúc không?

**Gợi ý:** cần phân biệt phạm vi thay đổi với tác động bảo mật. Có thể không sửa quy trình trong bản phát hành hiện tại, nhưng rủi ro đối với chức năng xuất vẫn cần được ghi nhận, giao chủ sở hữu và xử lý hoặc quyết định đúng thẩm quyền.

### Bài 2: Đọc đúng quyết định ngoại lệ

Yêu cầu thu hồi quyền trong 60 giây chưa đạt. Một quyết định tạm thời cho phép dùng thiết kế hiện tại trong 14 ngày, với phạm vi sử dụng và kiểm soát bổ sung đã xác định.

Trạng thái yêu cầu có thành đạt không?

**Gợi ý:** không. Cần ghi yêu cầu chưa đạt, liên kết ngoại lệ, điều kiện, người quyết định và ngày hết hạn. Đến hạn phải có hành động; không tự gia hạn.

### Bài 3: Viết lại một loại trừ mơ hồ

Câu ban đầu:

> “Không chịu trách nhiệm bảo mật kho lưu trữ.”

Hãy viết lại theo các trường: phạm vi gốc, phần không kiểm tra, lý do, phần tích hợp vẫn kiểm tra, giả định, chủ sở hữu và điều kiện xem xét lại.

**Gợi ý:** không kiểm tra nội bộ hạ tầng do nhà cung cấp vận hành; vẫn kiểm tra quyền tài khoản máy, điều kiện tải, cách ly tenant, dữ liệu gửi và hành vi lỗi trong phạm vi ứng dụng.

### Bài 4: Nhận diện rủi ro còn lại

Người dùng hợp lệ tải một tệp đã được kiểm tra quyền rồi chia sẻ bản sao ra ngoài. Nhóm đã đáp ứng các yêu cầu kiểm soát máy chủ theo phạm vi đã đặt.

Có thể vẫn còn rủi ro không?

**Gợi ý:** có. Cần đánh giá rủi ro sử dụng dữ liệu sau tải theo tài sản và nghĩa vụ áp dụng. Việc yêu cầu trong phạm vi đã đạt không tự chứng minh mọi đường gây tổn thất đã được loại bỏ.

### Bài 5: Phân biệt chưa biết và thấp

Bản sao lưu do nhóm khác quản lý. Nhóm ứng dụng chưa biết ai có quyền giải mã nhưng ghi “rủi ro thấp vì ngoài phạm vi”.

**Gợi ý:** đây là thông tin thiếu cần xác minh. Cần xác định trách nhiệm, quyền dùng khóa, phạm vi dữ liệu và khả năng phục hồi; không suy ra mức thấp từ việc không đánh giá.

## 16. Các câu hỏi để chốt phạm vi và bàn giao

1. Mỗi phát biểu out-of-scope đã nêu rõ loại phạm vi chưa?
2. Phần loại trừ có đang che một nghĩa vụ áp dụng hoặc một lỗi đã biết không?
3. Các ranh giới dữ liệu, danh tính, phân quyền, logging và phục hồi còn giữ nghĩa vụ nào?
4. Giả định nào đã có bằng chứng, giả định nào còn thiếu?
5. Rủi ro hiện tại đã được tách khỏi mức dự kiến sau xử lý chưa?
6. Yêu cầu chưa đạt có được báo cáo đúng trạng thái không?
7. Ai sở hữu rủi ro, ai có quyền quyết định và quyết định còn hiệu lực đến khi nào?
8. Điều kiện nào phải duy trì và thay đổi nào buộc đánh giá lại?
9. Báo cáo có giới hạn kết luận theo phiên bản, môi trường và bằng chứng thực tế không?

Một phạm vi rõ giúp công việc có thể thực hiện và nghiệm thu. Một hồ sơ rủi ro rõ giúp người có trách nhiệm hiểu phần bảo vệ đã đạt, phần chưa biết và phần còn phải quyết định. Khi hai phần được liên kết với yêu cầu và bằng chứng, việc loại trừ trở thành một quyết định minh bạch thay vì một khoảng trống trong thiết kế bảo mật.
