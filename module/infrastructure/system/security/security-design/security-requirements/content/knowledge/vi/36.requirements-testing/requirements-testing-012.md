# Resilience test: kiểm thử khả năng chống chịu và phục hồi an toàn

## 1. Mục tiêu bài học

**Resilience test** là kiểm thử cách hệ thống duy trì các chức năng cần thiết, suy giảm có kiểm soát và phục hồi khi xảy ra lỗi hoặc gián đoạn. Trong kiểm thử yêu cầu bảo mật, câu hỏi không chỉ là “dịch vụ còn trả lời không” mà còn là:

> Khi một thành phần không hoạt động như dự kiến, hệ thống có tiếp tục bảo vệ danh tính, quyền, dữ liệu và khả năng truy vết; sau đó có trở về trạng thái được chấp nhận trong giới hạn đã cam kết không?

Một hệ thống luôn trả 200 nhưng bỏ kiểm tra quyền khi dịch vụ phân quyền bị lỗi không có hành vi chống chịu an toàn. Một hệ thống từ chối mọi yêu cầu vô thời hạn cũng chưa đáp ứng mục tiêu duy trì hoạt động, dù nó không trả dữ liệu trái phép.

Học xong bài này, bạn có thể:

- Chuyển rủi ro gián đoạn thành yêu cầu chống chịu và phục hồi có thể kiểm chứng.
- Xác định bất biến bảo mật, chế độ suy giảm, ngân sách thời gian và điều kiện phục hồi.
- Thiết kế lỗi có kiểm soát, quan sát đúng đường xử lý và phân biệt lỗi sản phẩm với lỗi môi trường thử.
- Kiểm tra timeout, retry, xử lý lặp, khởi động lại worker, audit và khôi phục dữ liệu.
- Liên kết kịch bản lỗi với yêu cầu, kiến trúc, kết quả đo và bằng chứng theo phiên bản.

Mã yêu cầu, thời hạn, tải và ngưỡng số trong bài đều là ví dụ của một dịch vụ giả định. Chúng không phải mức bắt buộc chung. Các thử nghiệm được thiết kế cho môi trường do nhóm quản lý, với danh tính, dữ liệu và bản sao dành riêng cho kiểm thử.

## 2. Resilience test kiểm chứng điều gì?

### 2.1. Ba chiều cần quan sát cùng nhau

1. **Trong lúc lỗi:** chức năng nào tiếp tục, chức năng nào bị giới hạn và kiểm soát bảo mật nào vẫn phải có hiệu lực?
2. **Trong quá trình chuyển trạng thái:** có mất dữ liệu, xử lý lặp, cấp quyền sai hoặc công bố kết quả chưa được phép không?
3. **Sau phục hồi:** hệ thống có thực sự sẵn sàng về nghiệp vụ và bảo mật, thay vì chỉ khởi động được tiến trình?

Ví dụ, worker xuất hồ sơ bị khởi động lại sau khi tạo tệp nhưng trước khi xác nhận hoàn tất. Khi nhận lại thông điệp, nó có thể tạo kết quả lặp hoặc công bố tệp cho người vừa bị thu hồi quyền. Kiểm thử cần quan sát cả trạng thái công việc lẫn quyền truy cập đầu ra.

### 2.2. Phân biệt các hoạt động liên quan

| Hoạt động | Trọng tâm | Giới hạn cần nhớ |
|---|---|---|
| Kiểm thử tải | Hành vi dưới một hồ sơ tải xác định | Tải cao không tự đại diện cho lỗi phụ thuộc hoặc khôi phục dữ liệu. |
| Kiểm thử failover | Chuyển sang thành phần hoặc nơi phục vụ thay thế | Chuyển thành công chưa chứng minh dữ liệu nhất quán và quyền vẫn đúng. |
| Kiểm thử khôi phục | Khôi phục dữ liệu, cấu hình và hoạt động | Backup báo thành công chưa chứng minh khôi phục đạt mục tiêu. |
| Fault injection | Chủ động đưa lỗi có kiểm soát vào điểm được chọn | Là kỹ thuật tạo điều kiện thử, không tự tạo ra tiêu chí đạt. |
| Chaos engineering | Thực nghiệm có giả thuyết để tìm điểm yếu của hệ thống | Cần phạm vi, quan sát và điều kiện dừng phù hợp; không thay thế đặc tả yêu cầu. |
| Resilience test | Kiểm chứng hành vi chống chịu, suy giảm và phục hồi theo yêu cầu | Kết luận phải gắn với mô hình lỗi và phạm vi đã thử. |

Một bài kiểm thử có thể dùng nhiều kỹ thuật. Giá trị nằm ở yêu cầu được kiểm chứng và bằng chứng thu được, không nằm ở mức độ nghiêm trọng của lỗi được tạo.

## 3. Bắt đầu từ rủi ro và mô hình lỗi

Không nên bắt đầu bằng “tắt ngẫu nhiên một máy”. Trước hết cần biết tài sản và thuộc tính bảo vệ nào có thể bị ảnh hưởng.

Ví dụ chuỗi truy vết:

```text
Tài sản và chức năng quan trọng
              |
              v
Kịch bản lỗi + điều kiện + thời lượng
              |
              v
Rủi ro đối với bí mật / toàn vẹn / sẵn sàng
              |
              v
Yêu cầu trong lúc lỗi và sau phục hồi
              |
              v
Điểm tạo lỗi + quan sát + oracle
              |
              v
Bằng chứng, thiếu hụt và quyết định xử lý
```

### 3.1. Mô hình lỗi phải đủ cụ thể

| Khía cạnh | Câu hỏi |
|---|---|
| Thành phần | Dịch vụ quyền, cơ sở dữ liệu, worker, kho tệp, bộ thu audit hay mạng giữa chúng? |
| Kiểu lỗi | Không phản hồi, chậm, trả lỗi, mất kết nối, đầy bộ đệm, khởi động lại hoặc mất dữ liệu? |
| Phạm vi | Một instance, một nhóm worker, một đường mạng hay một kho dữ liệu thử? |
| Thời điểm | Trước quyết định quyền, sau ghi dữ liệu, trước xác nhận thông điệp hay lúc công bố tệp? |
| Thời lượng | Lỗi ngắn, kéo dài hoặc chập chờn theo lịch thử? |
| Trạng thái ban đầu | Có bao nhiêu tác vụ đang chờ, cache còn mới không, dữ liệu nào đã được xác nhận ghi? |
| Điều kiện phục hồi | Gỡ lỗi có đủ hay còn phải đồng bộ, xử lý hàng đợi và kiểm tra dữ liệu? |

Một phụ thuộc trả lỗi nhanh và một phụ thuộc không phản hồi có thể tạo hậu quả khác nhau. Cần thử đúng kiểu lỗi mà yêu cầu và kiến trúc phải xử lý.

### 3.2. Ưu tiên theo rủi ro

Các kịch bản thường đáng xem xét gồm:

- Lỗi làm mất căn cứ xác thực hoặc quyết định quyền.
- Khởi động lại tại điểm có thể gây tác dụng phụ lặp.
- Mất kênh audit trong lúc có thao tác đặc quyền.
- Bản sao lưu hoặc khóa không sử dụng được khi cần khôi phục.
- Một phụ thuộc chậm làm cạn tài nguyên và lan sang chức năng khác.
- Dữ liệu phục hồi chứa quyền cũ hoặc trạng thái tác vụ không còn đúng.

Không cần thử mọi tổ hợp cùng lúc. Bắt đầu với lỗi đơn có nguyên nhân rõ, sau đó chọn tổ hợp thực tế theo rủi ro và khả năng quan sát.

## 4. Đặc tả yêu cầu trước khi thiết kế phép thử

Một mẫu diễn đạt hữu ích:

> Với [hồ sơ tải và trạng thái ban đầu], khi [lỗi] xảy ra tại [ranh giới], hệ thống phải giữ [bất biến bảo mật], duy trì hoặc giới hạn [chức năng] theo [chế độ suy giảm], trong [ngân sách]. Khi [điều kiện lỗi được gỡ], hệ thống phải trở lại [trạng thái chấp nhận] và cung cấp [bằng chứng].

### 4.1. Bất biến bảo mật

Bất biến là thuộc tính phải được giữ trong phạm vi đã đặc tả, kể cả khi có lỗi:

- Không trả dữ liệu tenant khác.
- Không cho phép thao tác nhạy cảm khi thiếu căn cứ cấp quyền hợp lệ.
- Không công bố nhiều kết quả nghiệp vụ cho cùng một thao tác logic nếu yêu cầu chỉ cho phép một.
- Không đưa token, khóa hoặc nội dung hồ sơ vào log lỗi.
- Không cho danh tính ứng dụng xóa hoặc đọc bản sao lưu ngoài quyền được cấp.
- Không mở dịch vụ sau khôi phục trước khi kiểm tra các điều kiện bảo vệ bắt buộc.

Các bất biến cần đi kèm điểm quan sát và oracle, không chỉ nằm trong phần mô tả mục tiêu.

### 4.2. Chế độ suy giảm có kiểm soát

Có thể quy định:

- Nội dung công khai vẫn đọc được.
- Thao tác cần quyền hiện hành bị từ chối nếu không thể xác minh đủ điều kiện.
- Tác vụ đã nhận được giữ bền vững và chưa công bố kết quả cho tới khi có quyết định hợp lệ.
- Bộ thu audit tạm mất kết nối được xử lý bằng bộ đệm bền vững có giới hạn.
- Khi không còn khả năng ghi audit bắt buộc, ngừng chấp nhận những thao tác đặc quyền bị ràng buộc bởi yêu cầu đó.

Không mặc định mọi lỗi đều phải làm toàn bộ hệ thống dừng. Cũng không mặc định có cache là được tiếp tục vô thời hạn.

### 4.3. Tham số phải có cách đo

| Tham số | Điều cần xác định |
|---|---|
| Timeout | Áp dụng cho bước nào, đo ở đâu và có bao gồm thời gian kết nối không? |
| Tổng thời hạn request | Tính từ lúc nào tới lúc nào, dưới tải và điều kiện mạng nào? |
| Retry | Tối đa bao nhiêu lần tính cả lần đầu, ở những tầng nào, với loại lỗi nào? |
| Độ mới của quyền | Nguồn có thẩm quyền là gì, giới hạn thu hồi được đo thế nào qua cache và đồng bộ? |
| Giới hạn bộ đệm | Dung lượng, hành vi khi đầy và tác động tới chức năng nào? |
| Thời gian phục hồi | Bắt đầu khi nào, kết thúc ở trạng thái nghiệp vụ nào? |
| Mức mất dữ liệu | Dữ liệu nào thuộc phạm vi, cách xác định điểm khôi phục nhất quán? |

Một cấu hình timeout đúng chưa chứng minh tổng thời gian phản hồi đúng. Một lần retry ở mỗi tầng có thể tạo nhiều lời gọi xuống dưới hơn nhóm dự kiến.

## 5. Dịch vụ minh họa và bộ yêu cầu

Xét dịch vụ hồ sơ nhiều tenant có API, nguồn quyền, worker xuất dữ liệu, kho tệp, hệ thống audit và sao lưu.

Bộ yêu cầu minh họa:

| Mã | Yêu cầu |
|---|---|
| RSL-AUTHZ-01 | Thao tác dữ liệu riêng phải bị từ chối khi không có căn cứ quyền hợp lệ theo chính sách; không dùng đường bỏ qua kiểm tra lúc phụ thuộc lỗi. |
| RSL-AUTHZ-02 | Quyết định quyền phải phản ánh thu hồi trong tối đa 60 giây từ lúc nguồn quyền có thẩm quyền ghi nhận thành công sự kiện. |
| RSL-TIME-01 | Trong hồ sơ tải thử đã định, request không thể quyết định quyền phải kết thúc có kiểm soát trong tối đa 2 giây đo tại client kiểm thử. |
| RSL-RETRY-01 | Trên đường kiểm tra quyền được xét, tổng số lời gọi tới phụ thuộc cho một request không vượt hai, tính cả lần đầu và retry ở các tầng liên quan. |
| RSL-JOB-01 | Khởi động lại hoặc nhận lại thông điệp không làm mất tác vụ đã được chấp nhận bền vững và không công bố kết quả nghiệp vụ lặp cho một operationId. |
| RSL-AUDIT-01 | Thao tác thay đổi quyền chỉ được chấp nhận khi có thể ghi audit bền vững theo thiết kế; mất bộ thu không được làm bộ đệm tăng vô hạn. |
| RSL-REC-01 | Trong kịch bản mất kho dữ liệu chính đã xác định, đạt RPO 15 phút và RTO 30 phút; chỉ mở lại sau kiểm tra dữ liệu và điều kiện bảo mật. |

Các con số được chọn để minh họa đặc tả. Chúng chỉ có ý nghĩa khi hồ sơ tải, phạm vi dữ liệu, kiến trúc và điều kiện thử được xác định.

RSL-JOB-01 không khẳng định thông điệp chỉ được giao một lần. Nó yêu cầu kết quả nghiệp vụ đúng dù thông điệp có thể được xử lý lại.

## 6. Thiết kế kế hoạch thử và đường cơ sở

### 6.1. Fixture và phạm vi

Chuẩn bị:

- Hai tenant với dữ liệu tổng hợp phân biệt được.
- Người dùng có quyền, người dùng không có quyền và một chủ thể để thử thu hồi quyền.
- Tác vụ có operationId riêng, dữ liệu đầu vào và đầu ra có thể đối chiếu.
- Danh tính observer để đọc trạng thái thử, tách khỏi danh tính thực hiện nghiệp vụ.
- Cấu hình, phiên bản ứng dụng và phụ thuộc được ghi nhận.
- Dữ liệu sao lưu, khóa và môi trường phục hồi dành riêng cho phép thử.
- Kênh quan sát không bị mất theo đúng thành phần đang được tạo lỗi, hoặc phương án thu thập thay thế đã xác định.

Đặt phạm vi lỗi tới đúng dịch vụ và tài nguyên thử. Điều kiện dừng cần dựa trên hành vi ngoài phạm vi, mức sử dụng tài nguyên, mất quan sát hoặc nguy cơ không kiểm soát được dữ liệu thử.

### 6.2. Chạy đường cơ sở không có lỗi

Trước khi tạo lỗi, xác minh:

1. Người có quyền hoàn tất thao tác hợp lệ.
2. Người không có quyền hoặc khác tenant bị từ chối.
3. Audit và mã tương quan được ghi đúng.
4. Worker xử lý được tác vụ, kết quả và quyền tải đúng.
5. Số lời gọi, thời gian phản hồi và trạng thái ban đầu đo được.
6. Đường tạo lỗi và kênh quan sát được nhận diện đúng.

Nếu đường cơ sở đã lỗi, việc nhận lỗi sau fault injection chưa chứng minh hành vi chống chịu. Cần giải quyết hoặc phân loại điều kiện đó trước khi diễn giải kết quả.

### 6.3. Tách chủ thể thử và observer

Request nghiệp vụ dùng đúng danh tính được mô hình hóa. Observer chỉ dùng để quan sát hoặc điều khiển fixture theo phạm vi được cấp.

Không dùng quyền quản trị của test harness để gọi thay người dùng rồi kết luận cơ chế phân quyền của người dùng đạt.

Dữ liệu quan sát phải gắn với lần chạy, requestId, operationId hoặc phạm vi tương đương để không nhầm với tác vụ của ca khác.


## 7. Tình huống A: nguồn quyết định quyền không phản hồi

### 7.1. Mục tiêu và giả thuyết

Mục tiêu là kiểm chứng RSL-AUTHZ-01, RSL-AUTHZ-02, RSL-TIME-01 và RSL-RETRY-01.

Giả thuyết:

> Khi đường gọi từ ứng dụng tới nguồn quyền không phản hồi, ứng dụng không bỏ kiểm tra quyền, không tiếp tục dùng dữ kiện quá giới hạn cho phép và không làm request hoặc retry kéo dài ngoài ngân sách.

Không mặc định mất kết nối tới nhà cung cấp danh tính đồng nghĩa mọi token đều không thể xác minh. Nếu thiết kế cho phép xác minh tại chỗ bằng dữ kiện còn hợp lệ, phải kiểm tra đúng điều kiện đó. Xác minh danh tính và quyết định quyền hiện hành cũng là hai vấn đề riêng.

### 7.2. Tiền điều kiện

- user-a có token hợp lệ, thuộc tenant-a và ban đầu có quyền đọc hồ sơ.
- Tài nguyên tenant-a và tenant-b tồn tại trong fixture.
- Chính sách nêu rõ nguồn quyền có thẩm quyền và giới hạn phản ánh thu hồi 60 giây.
- Hồ sơ tải, số client và dữ liệu thử được cố định.
- Kênh tạo lỗi chỉ chặn đường gọi quyền của ứng dụng; kênh điều khiển fixture vẫn có thể ghi nhận thu hồi tại nguồn.
- Observer đo được lời gọi xuống phụ thuộc, trạng thái nghiệp vụ và thời gian tại client.

Dữ kiện trong cache chỉ được dùng khi đáp ứng điều kiện chính sách. TTL của một cache không tự chứng minh giới hạn thu hồi toàn luồng, vì dữ liệu lấy về có thể đã cũ hoặc còn tầng cache khác.

### 7.3. Các bước

1. Chạy ca đọc hợp lệ và ca truy cập chéo tenant để xác nhận đường cơ sở.
2. Ghi nhận trạng thái quyền và dữ kiện cache liên quan.
3. Đưa lỗi không phản hồi vào đúng đường gọi quyền.
4. Thu hồi quyền user-a tại nguồn có thẩm quyền và ghi nhận thời điểm t0.
5. Gửi request trong các giai đoạn cần xét, gồm sau thời điểm phải phản ánh thu hồi.
6. Đo thời gian request và tổng lời gọi tới nguồn quyền.
7. Kiểm tra phản hồi, dữ liệu, công việc được tạo và audit theo chính sách.
8. Gỡ lỗi, kiểm tra ứng dụng tiếp tục dùng trạng thái quyền đúng thay vì phục hồi quyền cũ.
9. Dùng một chủ thể khác còn quyền để kiểm tra chức năng hợp lệ phục hồi.

Có thể có trường hợp từ chối sớm ngay khi mất căn cứ quyền. Điều đó không vi phạm giới hạn 60 giây, vốn là giới hạn tối đa cho thu hồi chứ không phải thời gian buộc phải chờ.

### 7.4. Oracle

- Không trả dữ liệu hoặc tạo tác dụng phụ được bảo vệ khi không có căn cứ cho phép hợp lệ.
- Sau giới hạn thu hồi, không dùng cache cũ để tiếp tục cấp quyền.
- Với request không thể quyết định quyền do phụ thuộc không khả dụng, trả kết quả theo hợp đồng, ví dụ 503 có mã tương quan và không có dữ liệu nhạy cảm.
- Không dùng lỗi 503 để che một request đã tạo tác vụ hoặc trả dữ liệu trước đó.
- Request thuộc kịch bản này kết thúc trong 2 giây theo điều kiện đo đã xác định.
- Tổng lời gọi xuống phụ thuộc không vượt hai cho một request trên đường được xét.
- Log lỗi không chứa token hoặc nội dung hồ sơ.
- Sau gỡ lỗi, chủ thể còn quyền được phục vụ; user-a đã bị thu hồi vẫn bị từ chối theo chính sách.

Phải phân biệt không xác minh được quyền với đã xác định chủ thể không có quyền. Hợp đồng có thể dùng mã khác nhau cho hai tình huống; test không nên chấp nhận tùy ý mọi mã lỗi.

### 7.5. Biến thể phản hồi tới muộn

Giữ một lời gọi quyền tới khi request nghiệp vụ đã hết hạn, sau đó cho phụ thuộc trả kết quả.

Kiểm tra kết quả tới muộn không làm request đã kết thúc tiếp tục tạo tác vụ hoặc công bố dữ liệu trái với vòng đời đã quy định. Việc client nhận timeout chưa chứng minh phía máy chủ không còn thực hiện tác dụng phụ.

Đối với tác vụ được phép tiếp tục sau khi client ngắt kết nối, phải có hợp đồng riêng về trạng thái được chấp nhận, operationId và cách tra cứu. Không đánh đồng mọi request bị ngắt với thao tác đã bị hủy.

## 8. Kiểm tra timeout, retry và giới hạn lan truyền lỗi

### 8.1. Timeout phải nằm trong ngân sách toàn đường

Một đường gọi có thể gồm chờ kết nối, gọi phụ thuộc, chờ retry và truy vấn dữ liệu. Tổng các giai đoạn phải phù hợp với yêu cầu của request.

Ví dụ cấu hình một lời gọi có hạn chờ 200 mili giây không chứng minh request kết thúc trong 2 giây nếu còn:

- DNS hoặc kết nối không bị ràng buộc như nhóm tưởng.
- Hàng đợi nội bộ dài.
- Retry ở client thư viện, proxy và ứng dụng.
- Công việc không phản ứng với hủy.
- Xử lý lỗi hoặc ghi log chặn quá lâu.

Test phải đo ở vị trí được yêu cầu và kiểm tra trace hoặc bằng chứng tương đương để giải thích thời gian.

### 8.2. Retry cần đúng loại thao tác

Retry có thể giúp vượt lỗi tạm thời, nhưng có thể tăng tải hoặc thực hiện lặp một thao tác đã thành công mà phía gọi chưa biết.

Cần xác định:

- Loại lỗi và thao tác được phép retry.
- Tổng số lần thử, tính cả lần đầu.
- Ngân sách còn lại trước mỗi lần thử.
- Cách giãn nhịp để tránh nhiều client cùng gọi lại dồn dập.
- Cách nhận diện một thao tác logic qua nhiều lần gửi.
- Hành vi khi kết quả lần trước chưa rõ.

Không retry một quyết định từ chối quyền như thể đó là lỗi kết nối tạm thời. Không giả định request ghi dữ liệu an toàn để gọi lại chỉ vì lần trước client nhận timeout.

### 8.3. Circuit breaker và cô lập tài nguyên

Nếu thiết kế có circuit breaker, có thể kiểm tra các trạng thái cho phép gọi, ngừng gọi khi lỗi và thử phục hồi có giới hạn. Cần xác minh:

- Khi ngừng gọi, hệ thống trả kết quả suy giảm đã định.
- Không chuyển sang đường cho phép bỏ kiểm tra quyền.
- Lượng request thăm dò phục hồi được giới hạn.
- Sau phục hồi, tải không dồn lên phụ thuộc vượt điều kiện đã cam kết.

Nếu có giới hạn pool, hàng đợi hoặc mức đồng thời, thử xem lỗi một phụ thuộc có làm cạn tài nguyên của chức năng khác không. Các giới hạn cần có hành vi khi đầy, thay vì chỉ là con số trong cấu hình.

Cấu hình cơ chế chống chịu không phải bằng chứng cơ chế có hiệu lực. Cần quan sát số lời gọi, tài nguyên, phản hồi và trạng thái nghiệp vụ khi lỗi diễn ra.

## 9. Tình huống B: worker dừng sau một tác dụng phụ

### 9.1. Rủi ro

Worker có thể nhận lại cùng một thông điệp sau khởi động lại. Nếu không quản lý trạng thái và thao tác logic phù hợp, hệ thống có thể:

- Tạo kết quả lặp.
- Mất tác vụ đã được chấp nhận.
- Để tệp mồ côi có thể truy cập.
- Công bố kết quả dựa trên quyền đã bị thu hồi.
- Đánh dấu thành công dù dữ liệu đầu ra chưa đầy đủ.

### 9.2. Các điểm cắt có ý nghĩa

| Điểm dừng worker | Điều cần kiểm chứng |
|---|---|
| Sau nhận thông điệp, trước xử lý | Công việc còn được tiếp tục hoặc kết thúc theo chính sách, không mất âm thầm. |
| Sau ghi trạng thái bền vững, trước xác nhận thông điệp | Nhận lại thông điệp không tạo thao tác nghiệp vụ thứ hai. |
| Sau tạo tệp, trước ghi nhận kết quả | Tệp tạm được bảo vệ; phục hồi không công bố sai hoặc bỏ quên ngoài vòng đời được duyệt. |
| Sau công bố kết quả, trước xác nhận hoàn tất | Xử lý lại không công bố thêm kết quả nghiệp vụ cho cùng operationId. |

Không cần chạy mọi điểm trong một lần thử. Tách ca để tái hiện và giải thích kết quả.

### 9.3. Thiết kế phép thử

1. Tạo một tác vụ hợp lệ với operationId riêng và nội dung tổng hợp có thể đối chiếu.
2. Xác nhận tác vụ đã được chấp nhận bền vững theo hợp đồng.
3. Cho worker tới đúng điểm cắt được quan sát.
4. Dừng hoặc khởi động lại worker trong phạm vi fixture.
5. Cho cơ chế tiếp nhận lại công việc hoạt động.
6. Theo dõi tới trạng thái kết thúc trong thời hạn đã đặc tả.
7. Kiểm tra trạng thái, kết quả, quyền tải, tệp tạm và sự kiện liên quan.

Giữ nguyên operationId qua các lần thử của cùng thao tác. Nếu mỗi lần nhận lại được coi là thao tác mới, test sẽ khó phân biệt retry với yêu cầu độc lập.

### 9.4. Oracle

- Tác vụ đã nhận không biến mất khỏi mọi trạng thái có thể giải thích.
- Với quyền vẫn hợp lệ và không còn lỗi, tác vụ đạt kết quả được quy định trong thời hạn áp dụng.
- Không có hơn một kết quả nghiệp vụ được công bố cho cùng operationId.
- Dữ liệu đầu ra nhất quán với đầu vào và đúng tenant.
- Tệp tạm, nếu cơ chế cho phép có nhiều bản, vẫn riêng tư và được xử lý theo vòng đời đã duyệt.
- Audit và trạng thái có thể liên kết các lần xử lý lại mà không nhầm thành nhiều yêu cầu độc lập.
- Không công bố kết quả nếu tại điểm phải kiểm tra, quyền không còn hợp lệ.

Một phép thử không thấy kết quả lặp chưa chứng minh thông điệp được giao đúng một lần. Kết luận cần bám vào kết quả nghiệp vụ quan sát được.

### 9.5. Biến thể thu hồi quyền khi phục hồi

Sau khi worker dừng, thu hồi quyền chủ thể trước khi cho tiếp tục. Khi tới điểm kiểm tra nằm sau giới hạn thu hồi, worker không được chỉ tin quyền chụp lúc tạo tác vụ.

Có thể kết thúc theo trạng thái từ chối hoặc hủy do chính sách, nếu đó là hành vi được đặc tả. Không buộc tác vụ thành công chỉ để thỏa điều kiện “không mất công việc”: công việc được kết thúc có lý do và không công bố dữ liệu trái phép là kết quả khác với bị mất âm thầm.


## 10. Mất bộ thu audit và bộ đệm đầy

### 10.1. Đặc tả hành vi trước khi thử

RSL-AUDIT-01 yêu cầu thao tác thay đổi quyền chỉ được chấp nhận khi audit được ghi bền vững theo thiết kế. Một phương án giả định là bộ đệm bền vững có giới hạn khi bộ thu từ xa không khả dụng.

Cần xác định:

- Điểm nào được coi là đã ghi audit bền vững.
- Bộ đệm chịu được loại lỗi nào.
- Giới hạn dung lượng và kích thước sự kiện.
- Thao tác nào bị ngừng khi không còn khả năng ghi.
- Cách tiếp tục chuyển sự kiện và đối soát sau phục hồi.
- Kênh báo tình trạng suy giảm.

Một bộ đệm còn sau khởi động lại tiến trình chưa chứng minh chịu được mất toàn bộ máy. Phạm vi bền vững phải khớp với mô hình lỗi đã cam kết.

### 10.2. Phép thử

1. Xác nhận thao tác thay đổi quyền hợp lệ tạo audit đúng.
2. Chặn đường tới bộ thu từ xa.
3. Thực hiện số thao tác thử trong phạm vi còn dung lượng bộ đệm.
4. Xác minh audit đã được ghi tại điểm bền vững được quy định.
5. Tăng tới giới hạn đã chọn bằng các sự kiện thử có kích thước kiểm soát.
6. Gửi thêm một thao tác thay đổi quyền.
7. Kiểm tra thao tác không được chấp nhận nếu không còn cách ghi audit bắt buộc.
8. Gỡ lỗi và đối soát các thao tác đã chấp nhận với sự kiện được chuyển.
9. Thử khởi động lại tiến trình khi có sự kiện đang đệm nếu đó thuộc phạm vi yêu cầu.

### 10.3. Oracle và các điểm dễ bỏ sót

- Không thay đổi quyền thành công rồi chỉ trả lỗi vì audit thất bại.
- Không bỏ qua audit để duy trì tỷ lệ request thành công.
- Bộ đệm không tăng vô hạn hoặc làm cạn tài nguyên ngoài giới hạn.
- Sự kiện của các thao tác đã được chấp nhận không bị mất trong phạm vi lỗi cam kết.
- Việc chuyển lại sự kiện có thể được đối soát theo eventId; nếu pipeline cho phép giao lặp, báo cáo phải phân biệt lần giao với sự kiện logic.
- Token, khóa và dữ liệu nhạy cảm không bị đưa vào log lỗi của chính pipeline.
- Khi bộ thu phục hồi, backlog được xử lý trong mục tiêu đã đặc tả và không làm mất khả năng phục vụ chức năng khác.

Không mặc định có thể ghi mọi sự kiện từ chối vào chính bộ đệm đã đầy. Nếu đặc tả yêu cầu ghi bền vững cả mọi lần từ chối trong điều kiện đó, kiến trúc phải có phương án đáp ứng phù hợp. Không dùng kỳ vọng bất khả thi rồi bỏ qua thất bại của test.

## 11. Tình huống C: khôi phục dữ liệu và mở lại dịch vụ

### 11.1. Định nghĩa RPO và RTO

- **RPO (Recovery Point Objective)** là mục tiêu mức mất dữ liệu chấp nhận được biểu diễn theo thời gian. Trong ví dụ, điểm dữ liệu nhất quán có thể khôi phục phải cách thời điểm sự cố không quá 15 phút.
- **RTO (Recovery Time Objective)** là mục tiêu thời gian đưa dịch vụ về mức hoạt động được chấp nhận. Trong ví dụ, thời gian này không quá 30 phút.

Hai mục tiêu áp dụng cho kịch bản mất kho dữ liệu chính đã chọn, không tự bao phủ mọi loại thảm họa hoặc tấn công.

Trong kế hoạch này, t0 là thời điểm dịch vụ mất khả năng phục vụ do lỗi thử, được kênh quan sát ghi nhận. Thời điểm kết thúc RTO là lúc đã hoàn tất tập kiểm tra chấp nhận để cho phép hoạt động, gồm nghiệp vụ và bảo mật. Không bắt đầu bấm giờ sau khi đã chờ người vận hành hoặc loại thời gian kiểm tra cuối khỏi phép đo.

### 11.2. Fixture để đo mức mất dữ liệu

Chuẩn bị dòng giao dịch thử có:

- operationId và thứ tự hoặc dấu mốc có thể đối chiếu.
- Thời điểm xác nhận ghi bền vững từ nguồn được xác định.
- Quan hệ dữ liệu giữa các thành phần cần giữ nhất quán.
- Bản ghi tham chiếu của test harness nằm ngoài phạm vi kho đang bị mất.
- Mật độ ghi đủ để đo được cửa sổ mất dữ liệu cần xét.

Không lấy timestamp lớn nhất của một dòng được khôi phục làm toàn bộ bằng chứng. Một dòng mới vẫn có thể tồn tại trong khi các giao dịch trước đó bị thiếu hoặc quan hệ dữ liệu không nhất quán.

Cần xác định điểm cắt nhất quán mà dữ liệu đã được phục hồi đầy đủ theo phạm vi và kiểm tra những khoảng thiếu không được phép.

### 11.3. Chuỗi thử

1. Xác nhận hoạt động bình thường và ghi nhận cấu hình sao lưu, khóa, phiên bản cùng nguồn phục hồi.
2. Tạo các thao tác thử, lưu bằng chứng xác nhận ghi.
3. Tạo lỗi làm kho dữ liệu chính của fixture không thể phục vụ; ghi t0.
4. Thực hiện quy trình phát hiện, quyết định và khôi phục như kế hoạch.
5. Khôi phục dữ liệu, cấu hình và các phụ thuộc cần thiết.
6. Đối chiếu dữ liệu với bản tham chiếu để xác định điểm khôi phục nhất quán.
7. Kiểm tra danh tính, quyền, tenant, khóa, audit, tác vụ và quyền tải.
8. Thực hiện tập giao dịch nghiệp vụ chấp nhận.
9. Ghi thời điểm đủ điều kiện mở lại và tính kết quả RPO, RTO.

Nếu bản sao hoặc khóa không dùng được, thời gian vẫn tiếp tục tính theo định nghĩa thử. Không kết luận đã khôi phục chỉ vì một tiến trình chạy hoặc cơ sở dữ liệu trả lời truy vấn.

### 11.4. Điều kiện bảo mật sau phục hồi

Trong tình huống giả định này, quyền đã bị thu hồi trước sự cố không được tự xuất hiện lại khi mở dịch vụ.

Cần xem xét:

- Dữ liệu sao lưu có thể chứa vai trò hoặc tài khoản cũ.
- Phiên và token trước sự cố có còn được chấp nhận đúng chính sách không.
- Nguồn danh tính hoặc quyền hiện hành nằm ở đâu.
- Có cần đối soát sự kiện thu hồi hoặc khóa tài khoản trước khi mở lại không.
- Tệp xuất, liên kết tải và tác vụ cũ có tương ứng với trạng thái đã phục hồi không.
- Khóa và bí mật được nạp đúng, không dùng cấu hình thử hoặc đường truy cập tạm ngoài thiết kế.
- Audit tiếp tục ghi được theo yêu cầu và không bị vô hiệu hóa để hoàn thành RTO.

RPO về dữ liệu nghiệp vụ không tự cho phép phục hồi lại mọi quyền cũ. Nếu yêu cầu bảo vệ trạng thái thu hồi nghiêm ngặt hơn cửa sổ mất dữ liệu thông thường, kiến trúc và kế hoạch đối soát phải đáp ứng riêng.

Khi chưa có căn cứ quyền hợp lệ, giữ chức năng liên quan trong chế độ an toàn đã quy định thay vì mở lại theo dữ kiện cũ.

### 11.5. Oracle phục hồi

- Điểm khôi phục nhất quán đạt RPO 15 phút.
- Dịch vụ đạt tập điều kiện chấp nhận trong RTO 30 phút.
- Dữ liệu và quan hệ thuộc phạm vi nhất quán.
- Chủ thể đúng quyền thực hiện được thao tác được phép.
- Chủ thể khác tenant hoặc đã bị thu hồi không nhận dữ liệu trái phép.
- Không công bố tệp hoặc kết quả của tác vụ có trạng thái chưa được xác minh.
- Nguồn và tính toàn vẹn của bản phục hồi được kiểm tra theo cơ chế đã chọn.
- Có đủ bằng chứng về thời gian, dữ liệu, cấu hình và quyết định mở lại.

Sao lưu mỗi 15 phút chưa chứng minh RPO 15 phút: lần lỗi, thời gian hoàn tất hoặc bản sao không dùng được có thể làm điểm phục hồi cũ hơn. Tương tự, máy khởi động trong 10 phút chưa chứng minh RTO 30 phút nếu còn 40 phút đối soát trước khi phục vụ an toàn.

## 12. Đặc tả một ca resilience test

Ví dụ dưới là cấu trúc hồ sơ, không phải cấu hình chạy trực tiếp:

```yaml
case_id: RES-AUTHZ-01
case_revision: rev-1
risk_ref: RISK-AUTHZ-DEPENDENCY-FAILURE
requirement_refs:
  - RSL-AUTHZ-01
  - RSL-AUTHZ-02
  - RSL-TIME-01
  - RSL-RETRY-01
scope:
  - API hồ sơ của môi trường kiểm thử
  - Đường gọi nguồn quyền
actor_fixture: user-a
fault:
  type: DEPENDENCY_NO_RESPONSE
  boundary: Ứng dụng tới nguồn quyết định quyền
  scope_limit: Chỉ các request thuộc lần chạy
preconditions:
  - Ca hợp lệ và ca chéo tenant không có lỗi đã đạt
  - Token chủ thể còn hợp lệ
  - Nguồn quyền và thời điểm thu hồi quan sát được
measurements:
  - Thời gian hoàn tất tại client
  - Tổng lời gọi phụ thuộc theo requestId
  - Quyết định quyền và tác dụng phụ
  - Hành vi sau gỡ lỗi
expected:
  unauthorized_data_or_effect: ABSENT
  revocation_bound_seconds: 60
  failed_request_deadline_seconds: 2
  max_downstream_attempts_including_first: 2
recovery:
  - Gỡ lỗi đúng đường gọi
  - Xác minh chủ thể còn quyền hoạt động
  - Xác minh quyền đã thu hồi không được phục hồi sai
stop_conditions:
  - Lỗi tác động ngoài phạm vi fixture
  - Không còn khả năng quan sát cần thiết
cleanup:
  - Gỡ cấu hình tạo lỗi
  - Đối chiếu trạng thái và thu bằng chứng
  - Dọn đúng tài nguyên của lần chạy
```

Khi triển khai bộ test, bổ sung hồ sơ tải cụ thể, cấu hình cache, thời lượng lỗi, cách đồng bộ thời gian và phương pháp quan sát. Thiếu các dữ kiện này sẽ làm kết quả khó tái hiện hoặc bị diễn giải quá rộng.

## 13. Thu thập bằng chứng và phân loại kết quả

### 13.1. Chứng minh lỗi đã thực sự xảy ra

Một lần thử có thể xanh vì fault injection không chạm đúng đường gọi. Cần bằng chứng rằng:

- Đúng thành phần và request bị tác động.
- Kiểu lỗi và thời lượng phù hợp kế hoạch.
- Ứng dụng thực sự đi qua đường cần kiểm chứng.
- Observer và công cụ đo vẫn hoạt động.
- Không có cấu hình hoặc dữ liệu đối chứng bị thay đổi ngoài dự kiến.

Nếu chỉ làm client mất mạng, chưa chắc đã tạo lỗi đường ứng dụng gọi nguồn quyền. Hai trường hợp này có rủi ro và oracle khác nhau.

### 13.2. Quan sát theo cùng chuỗi nhân quả

Liên kết requestId, operationId, eventId và mốc thời gian phù hợp. Đối chiếu:

- Phản hồi cho client.
- Trạng thái dữ liệu và công việc bền vững.
- Hàng đợi, tệp và quyền tải.
- Lời gọi xuống phụ thuộc.
- Audit và chỉ dấu tài nguyên.
- Trạng thái sau khi gỡ lỗi.

Với xử lý bất đồng bộ, dùng trạng thái kết thúc, checkpoint hoặc điều kiện hoàn tất đã xác định. Một sleep cố định rồi không thấy tệp chưa đủ chứng minh không có kết quả trái phép xuất hiện sau đó.

### 13.3. Đọc kết quả theo từng chiều

| Chiều | Câu hỏi |
|---|---|
| Bảo mật | Có vượt quyền, lộ dữ liệu, trạng thái sai hoặc mất điều kiện audit bắt buộc không? |
| Nghiệp vụ | Chức năng nào tiếp tục, chức năng nào bị ngừng và có đúng chế độ suy giảm không? |
| Thời gian và tài nguyên | Có vượt deadline, số lần thử, bộ đệm hoặc mức đồng thời không? |
| Phục hồi | Có trở lại trạng thái được chấp nhận, đúng dữ liệu và đúng quyền không? |

Từ chối có kiểm soát một request hợp lệ có thể đúng yêu cầu bảo mật trong một khoảng suy giảm cho phép. Tuy nhiên, cần báo rõ chức năng bị ảnh hưởng. Không tính mọi 503 là thành công nghiệp vụ chỉ vì không lộ dữ liệu.

Ngược lại, request trái phép bị từ chối đúng không nên bị diễn giải như một lỗi khả dụng thông thường. Phân loại loại lưu lượng và tiêu chí trước khi tính tỷ lệ.

### 13.4. Trạng thái lần chạy

- **PASS:** tiền điều kiện và lỗi thử hợp lệ; các tiêu chí trong phạm vi đều đạt.
- **FAIL:** có bằng chứng vi phạm yêu cầu, kể cả lỗi thời gian hoặc phục hồi chứ không chỉ rò rỉ dữ liệu.
- **BLOCKED:** chưa thể thực hiện do thiếu môi trường, fixture hoặc phụ thuộc cần thiết.
- **INCONCLUSIVE:** đã thử nhưng mất căn cứ quan sát hoặc không xác nhận được lỗi đúng kế hoạch.
- **NOT RUN:** chưa chạy.

Một timeout do công cụ thu bằng chứng bị hỏng không tự chứng minh ứng dụng vi phạm deadline. Một request vượt deadline đã đo đúng trong môi trường hợp lệ cũng không được đổi thành lỗi công cụ chỉ để tránh FAIL.

Giữ bằng chứng của lần thất bại. Không chạy lại tới khi xanh rồi bỏ qua nguyên nhân chưa được giải thích.


## 14. Truy vết kết quả và duy trì bộ kiểm thử

### 14.1. Ma trận kế hoạch

| Ca | Kịch bản | Yêu cầu chính | Bằng chứng cần có |
|---|---|---|---|
| RES-AUTHZ-01 | Nguồn quyền không phản hồi, có thu hồi quyền | AUTHZ-01, AUTHZ-02, TIME-01, RETRY-01 thuộc bộ RSL | Trace lời gọi, thời gian, quyền, phản hồi, dữ liệu và hành vi sau gỡ lỗi. |
| RES-JOB-01 | Worker dừng trước xác nhận hoàn tất | RSL-JOB-01, RSL-AUTHZ-01 | Trạng thái bền vững, operationId, kết quả công bố, tệp tạm và quyết định quyền. |
| RES-AUDIT-01 | Mất bộ thu, bộ đệm tới giới hạn | RSL-AUDIT-01 | Thao tác đã chấp nhận, bản ghi audit bền vững, dung lượng và đối soát sau phục hồi. |
| RES-REC-01 | Mất kho dữ liệu chính của fixture | RSL-REC-01 cùng bất biến quyền và tenant | Dữ liệu tham chiếu, điểm cắt nhất quán, thời gian và tập kiểm tra mở lại. |

Đây là kế hoạch bao phủ, chưa phải kết quả thực thi. Khi quản lý lần chạy, phải gắn mã đầy đủ, phiên bản yêu cầu, phiên bản ca, build, cấu hình và môi trường.

Một yêu cầu có một ca liên kết chưa chắc đã được bao phủ đầy đủ. Ví dụ, lỗi nguồn quyền được thử tại API chưa chứng minh worker và đường tải tệp có cùng hành vi.

### 14.2. Khi nào cần đánh giá lại?

- Đổi nguồn danh tính, quyền hoặc chính sách cache.
- Thêm một tầng retry, proxy hay đường gọi dự phòng.
- Thay cơ chế hàng đợi, xác nhận thông điệp hoặc lưu trạng thái.
- Đổi vị trí và vòng đời tệp xuất.
- Đổi giới hạn bộ đệm hoặc điểm được coi là ghi audit bền vững.
- Đổi dữ liệu, khóa, công cụ sao lưu hoặc kiến trúc phục hồi.
- Đổi RPO, RTO, deadline hoặc chế độ suy giảm.
- Sự cố thực tế chỉ ra một giả định thử không đúng.

Giữ lịch sử ca và kết quả. Báo cáo của cấu hình cũ có thể còn giá trị lịch sử nhưng không tự chứng minh cấu hình mới.

Sau khi sửa lỗi, chạy lại ca tái hiện và phần hồi quy có tác động. Chỉ mở rộng thêm khi thay đổi, kết quả hoặc rủi ro còn chưa rõ tạo ra nhu cầu kiểm chứng cụ thể.

## 15. Những lỗi kết luận thường gặp

| Lỗi | Vì sao thiếu căn cứ | Cách điều chỉnh |
|---|---|---|
| Chỉ xem tiến trình còn chạy | Chưa biết nghiệp vụ và quyền có đúng không | Dùng tập kiểm tra chức năng và bảo mật có dữ liệu đối chứng. |
| Thấy 503 là kết luận an toàn | Tác dụng phụ có thể đã xảy ra trước hoặc sau phản hồi | Theo dõi dữ liệu, tác vụ, tệp và điểm hoàn tất. |
| Có cache nên cho phép mãi khi nguồn quyền lỗi | Không giữ giới hạn thu hồi hoặc độ mới | Kiểm chứng điều kiện dùng dữ kiện và điểm phải từ chối. |
| Chỉ đếm retry ở một thư viện | Proxy hoặc tầng khác có thể gọi lại | Đếm toàn đường theo request và ngân sách đã định. |
| Client timeout nên coi thao tác bị hủy | Phía máy chủ có thể tiếp tục | Kiểm tra vòng đời thao tác và tác dụng phụ tới muộn. |
| Có hai tệp tạm nên mặc định có hai kết quả nghiệp vụ | Tệp riêng tư có thể là chi tiết triển khai được cho phép | Đối chiếu số kết quả công bố và vòng đời tệp với yêu cầu. |
| Backup thành công nên coi RPO đạt | Bản sao có thể cũ, thiếu hoặc không dùng được | Khôi phục và đối chiếu điểm dữ liệu nhất quán. |
| Tính RTO từ lúc bắt đầu chạy lệnh restore | Bỏ thời gian phát hiện, quyết định hoặc chờ theo định nghĩa áp dụng | Xác định t0 và điều kiện kết thúc trước khi thử. |
| Mở lại ngay khi health check xanh | Có thể chưa đúng quyền, khóa, audit hoặc dữ liệu | Chỉ mở sau tập tiêu chí chấp nhận. |
| Không thấy lỗi nên coi fault injection thành công | Có thể chưa tác động đúng đường | Thu bằng chứng lỗi thực sự xảy ra và ứng dụng đi qua đường đó. |
| Gỡ lỗi là coi đã dọn xong | Cache, backlog hoặc trạng thái tạm vẫn có thể tồn tại | Đối soát trạng thái sau phục hồi và gỡ đúng cấu hình thử. |

## 16. Bài tập thực hành: đọc bằng chứng của một lần thử

Dịch vụ hồ sơ dùng bộ yêu cầu ở phần 5. Một nhóm báo cáo những quan sát sau trong các ca riêng:

1. Khi nguồn quyền không phản hồi, API trả 503 trong 1,4 giây, nhưng sau đó có tệp được công bố và user-a đã mất quyền tải được tệp.
2. Trace của một request có sáu lời gọi tới nguồn quyền; cấu hình của một thư viện ghi “retry một lần”.
3. Worker khởi động lại tạo hai tệp tạm riêng tư, nhưng chỉ một kết quả được công bố cho operationId; tệp tạm được xử lý đúng thời hạn đã duyệt.
4. Sau khôi phục, tiến trình chạy ở phút thứ 8, nhưng tới phút thứ 35 mới hoàn tất kiểm tra quyền và giao dịch chấp nhận.
5. Điểm khôi phục nhất quán cách t0 là 18 phút, dù lịch sao lưu được cấu hình mỗi 15 phút.
6. Một ca không có trace về lỗi phụ thuộc, đường cơ sở không chạy và tất cả request đều trả lỗi kết nối từ client.

Hãy thực hiện:

- Phân loại từng quan sát theo yêu cầu bị ảnh hưởng.
- Chỉ ra kết quả nào có thể FAIL, kết quả nào chưa đủ căn cứ và kết quả nào chưa phải lỗi theo đặc tả.
- Giải thích vì sao một tiêu chí thời gian đạt không bù được vi phạm phân quyền.
- Viết lại bằng chứng cần thu cho trường hợp 6.
- Đề xuất một biến thể kiểm thử thu hồi quyền trong khi worker dừng.
- Lập điều kiện đóng ca phục hồi, gồm dữ liệu, quyền, audit và giao dịch nghiệp vụ.
- Nêu phần cần chạy lại nếu thay đổi cách retry ở proxy hoặc nguồn quyền.

### Gợi ý tự đánh giá

- Trường hợp 1 có thể đạt tiêu chí thời gian nhưng vi phạm bất biến quyền và dữ liệu. Phải báo riêng từng chiều và kết quả tổng hợp theo quy tắc đã định.
- Trường hợp 2 vượt giới hạn hai lời gọi theo bộ yêu cầu; cấu hình một tầng không thay thế được trace toàn đường.
- Trường hợp 3 không tự động vi phạm điều kiện một kết quả nghiệp vụ nếu tệp tạm thực sự được bảo vệ và xử lý đúng vòng đời. Cần đối chiếu thêm các tiêu chí còn lại trước khi kết luận toàn ca PASS.
- Trường hợp 4 không đạt RTO 30 phút theo định nghĩa kết thúc trong bài; thời điểm tiến trình chạy không phải thời điểm đủ điều kiện mở lại.
- Trường hợp 5 không đạt RPO 15 phút. Tần suất cấu hình không thay thế kết quả khôi phục.
- Trường hợp 6 chưa chứng minh lỗi đường ứng dụng gọi nguồn quyền. Cần xác nhận đường cơ sở, điểm tạo lỗi, khả năng quan sát và trạng thái ứng dụng.

## 17. Câu hỏi tự kiểm tra

1. Vì sao hệ thống trả lời request liên tục vẫn có thể không chống chịu an toàn?
2. Fail closed đối với một thao tác nhạy cảm khác với dừng toàn bộ hệ thống như thế nào?
3. Cần những dữ kiện gì để quyết định có được dùng quyền trong cache khi phụ thuộc lỗi?
4. Tại sao deadline của client không tự chứng minh thao tác đã bị hủy?
5. Khi nào xử lý lặp thông điệp vẫn có thể đáp ứng yêu cầu một kết quả nghiệp vụ?
6. Vì sao bộ đệm audit bền vững cần được mô tả cùng phạm vi lỗi?
7. RPO và RTO cần được đo từ dữ liệu và mốc nào?
8. Vì sao khôi phục dữ liệu có thể làm xuất hiện lại một rủi ro về quyền đã thu hồi?
9. Cần chứng minh gì trước khi dùng một lần fault injection để kết luận?
10. Khi nào báo cáo nên là BLOCKED hoặc INCONCLUSIVE thay vì PASS hay FAIL?

