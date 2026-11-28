# Credential ownership

## Mục tiêu bài học

Trong chương **Credential management**, credential ownership là việc xác định ai chịu trách nhiệm về nhu cầu tồn tại, cách sử dụng và vòng đời của một credential. Trách nhiệm này phải được gắn với đúng tài khoản, hệ thống đích, bên phụ thuộc và cơ chế xử lý khi có thay đổi hoặc sự cố.

Trong **Privileged Access Management (PAM)**, credential có thể phục vụ tài khoản quản trị, tài khoản dịch vụ và hạ tầng nhạy cảm. Ownership rõ ràng là đầu vào để kiểm kê quyền, thực hiện least privilege, lựa chọn JIT/JEA, vận hành vault, luân chuyển credential, giám sát phiên và lưu bằng chứng phục vụ kiểm toán, ứng phó sự cố.

**Một credential đã nằm trong vault vẫn có thể chưa có owner hợp lệ. Người quản trị kho không tự trở thành người chịu trách nhiệm về mọi nhu cầu sử dụng bí mật trong kho.**

Sau bài học, bạn có thể:

- Phân biệt ownership với quyền đọc bí mật và quyền quản trị kỹ thuật.
- Ánh xạ credential tới tài khoản, tài nguyên, dịch vụ và các bên sử dụng.
- Xác lập owner có thẩm quyền, còn hiệu lực và có khả năng nhận việc.
- Phân công trách nhiệm trong rotation, thu hồi và xử lý sự cố.
- Chuyển giao ownership mà không bỏ sót quyền hoặc credential cũ.
- Xử lý credential chưa rõ owner và đo độ bao phủ ownership bằng bằng chứng.

## 1. Ownership thực sự có nghĩa gì?

Credential owner là đầu mối được tổ chức giao trách nhiệm bảo đảm credential được quản lý phù hợp với mục đích đã chấp nhận.

Tùy mô hình tổ chức, owner có thể là chủ sở hữu dịch vụ, account owner hoặc một vai trò chuyên trách. Điều quan trọng là trách nhiệm được xác định rõ, có thẩm quyền tương ứng và phân giải được tới người hoặc nhóm đang nhận việc.

Các trách nhiệm thường gồm:

1. Giải thích credential còn cần cho nhiệm vụ nào.
2. Xác định tài khoản và tài nguyên liên quan.
3. Duy trì danh sách bên phụ thuộc trong phạm vi quản lý.
4. Phối hợp review quyền và đường sử dụng.
5. Bảo đảm có kế hoạch rotation, thu hồi và phục hồi phù hợp.
6. Xử lý hoặc chuyển đúng thẩm quyền khi có cảnh báo, ngoại lệ hay sự cố.
7. Chuyển giao trách nhiệm khi dịch vụ, con người hoặc cơ cấu tổ chức thay đổi.

Owner không nhất thiết tự thực hiện mọi thao tác. Đội PAM có thể chạy rotation, đội ứng dụng cập nhật cấu hình và đội bảo mật điều phối điều tra. Ownership bảo đảm những phần việc đó có người chịu trách nhiệm kết nối và theo dõi đến kết quả.

### Những điều ownership không tự cấp

| Nhãn hoặc trách nhiệm | Không tự đồng nghĩa với |
| --- | --- |
| Owner của credential | Được xem giá trị bí mật bất cứ lúc nào |
| Owner của dịch vụ | Được tự cấp mọi quyền trên tài nguyên |
| Người tạo credential | Owner dài hạn đã được xác nhận |
| Người quản trị vault | Hiểu và chịu trách nhiệm mọi phụ thuộc ứng dụng |
| Người được dùng credential | Được sửa owner, policy hoặc quy trình phê duyệt |
| Người chấp nhận rủi ro | Được thực hiện mọi thay đổi kỹ thuật ngoài phạm vi ủy quyền |

Nếu một hệ thống dùng trường owner làm đầu vào phân quyền, hành vi đó phải được thiết kế rõ và kiểm soát riêng. Không để một thay đổi metadata trở thành cách tự cấp quyền đọc bí mật.

## 2. Phân biệt tài khoản, credential và phiên bản

Một principal có thể có nhiều credential. Một credential cũng có thể đang bị nhiều bên dùng chung. Vì vậy, chỉ gắn owner vào tên tài khoản thường chưa đủ.

~~~text
Dịch vụ và tài nguyên
        |
        v
Principal / tài khoản
        |
        +--> Credential A --> phiên bản hiện tại và lịch sử
        |
        +--> Credential B --> phiên bản hiện tại và lịch sử
        |
        +--> Cơ chế nhận danh tính khác
                    |
                    v
            Các bên sử dụng
~~~

Ví dụ, một tài khoản dịch vụ có hai khóa truy cập, mỗi khóa đang được dùng bởi một hệ thống khác nhau. Account owner có thể giống nhau, nhưng thông tin phụ thuộc và kế hoạch chuyển đổi của từng khóa phải được theo dõi.

### Những quan hệ cần biết

| Quan hệ | Câu hỏi |
| --- | --- |
| Credential với principal | Credential xác thực cho danh tính nào? |
| Principal với tài nguyên | Danh tính có thể tác động tới đâu? |
| Credential với nguồn cấp | Nơi nào có thẩm quyền phát hành, đổi hoặc thu hồi? |
| Credential với bên sử dụng | Ứng dụng, job, người hoặc broker nào nhận và dùng? |
| Credential với vault | Bản ghi nào quản lý, phiên bản và policy nào áp dụng? |
| Credential với owner | Ai chịu trách nhiệm và từ thời điểm nào? |

Hai bản ghi vault có thể vô tình tham chiếu cùng một credential ở đích. Nếu mỗi bản ghi được giao owner khác nhau và rotation độc lập, hệ thống có thể lệch trạng thái. Cần đối soát quan hệ thực tế trước khi coi chúng là hai đối tượng độc lập.

Không so sánh hoặc phát tán giá trị bí mật chỉ để nhận diện quan hệ. Ưu tiên ID gốc, tham chiếu quản lý và bằng chứng được bảo vệ theo khả năng hệ thống.

## 3. Các vai trò liên quan cần được tách rõ

| Vai trò | Trách nhiệm chính |
| --- | --- |
| Credential owner | Điều phối nhu cầu, phụ thuộc và vòng đời của credential được giao |
| Account owner | Chịu trách nhiệm mục đích và vòng đời principal |
| Resource owner | Xác nhận phạm vi quyền được chấp nhận trên tài nguyên |
| Chủ sở hữu dịch vụ hoặc kỹ thuật | Xác nhận cách dùng, phụ thuộc, tác động và phục hồi dịch vụ |
| Consumer owner | Chịu trách nhiệm một ứng dụng, job hoặc bên đang dùng credential |
| Đội vận hành PAM hoặc custodian | Vận hành vault, connector, policy và thao tác được giao |
| Người phê duyệt truy cập | Quyết định yêu cầu trong phạm vi được ủy quyền |
| Đội bảo mật hoặc ứng phó | Phân tích rủi ro, giám sát và xử lý sự cố theo quy trình |
| Người có thẩm quyền chấp nhận rủi ro | Quyết định ngoại lệ trong phạm vi tổ chức giao |

Một người có thể giữ nhiều vai trò, nhưng cần kiểm tra xung đột trong từng hành động. Khác tên vai trò không tạo ra độc lập nếu cùng một người vừa yêu cầu, tự duyệt và tự thay policy.

### Một đầu mối chịu trách nhiệm cho mỗi đối tượng

Một mô hình dễ vận hành là có một đầu mối ownership chính cho mỗi credential trong phạm vi xác định, kèm những bên phối hợp và đại diện dự phòng.

Điều này không có nghĩa đầu mối đó thay thế mọi thẩm quyền. Resource owner vẫn quyết định phạm vi quyền trên tài nguyên; consumer owner vẫn phải xác nhận việc chuyển đổi của ứng dụng mình.

Nếu một credential phục vụ nhiều dịch vụ, cần đánh giá khả năng tách. Khi chưa tách được, phải có đầu mối điều phối chung và trách nhiệm cụ thể của từng bên. Ghi “nhiều đội cùng sở hữu” mà không có người nhận việc thường chỉ che khoảng trống.

## 4. Hợp đồng ownership tối thiểu

Một bản ghi ownership cần giúp người khác biết phải liên hệ ai, vì việc gì và với thẩm quyền nào.

| Nhóm thông tin | Nội dung cần có |
| --- | --- |
| Định danh | ID credential, principal và hệ thống hoặc nguồn xác thực |
| Phạm vi | Môi trường, tài nguyên, loại credential, mục đích sử dụng |
| Trách nhiệm | Vai trò owner, nhóm chịu trách nhiệm, người tiếp nhận hiện tại |
| Thẩm quyền | Nguồn chỉ định, bằng chứng chấp nhận, phạm vi ủy quyền |
| Hiệu lực | Thời điểm bắt đầu, trạng thái, lịch hoặc điều kiện review |
| Phối hợp | Resource owner, technical owner và các consumer owner |
| Vòng đời | Chính sách rotation, thu hồi, xác minh và xử lý lỗi |
| Dự phòng | Người hoặc nhóm thay thế, giới hạn ủy quyền và escalation |
| Bằng chứng | Tham chiếu quyết định, thay đổi và kết quả xác minh |

Không điền giá trị mật khẩu, token hoặc khóa riêng vào bản ghi ownership. Ngay cả metadata cũng cần giới hạn quyền xem vì nó mô tả các đường đặc quyền.

### Một mailbox chưa đủ

Mailbox nhóm hoặc kênh hỗ trợ có ích cho liên hệ, nhưng cần thêm:

- Cơ chế giao việc.
- Người đang chịu trách nhiệm tiếp nhận.
- Người có quyền quyết định.
- Đường chuyển tiếp khi không phản hồi.
- Cách duy trì thành viên và đại diện khi thay đổi nhân sự.

Nếu mọi thông báo được gửi nhưng không có ai nhận trách nhiệm, hệ thống chưa giải quyết được ownership.

## 5. Xác lập owner bằng bằng chứng

### 5.1. Thu thập ứng viên

Có thể tìm owner ứng viên từ hồ sơ dịch vụ, người bảo trợ tài khoản, cấu hình triển khai, tham chiếu ứng dụng, lịch sử thay đổi hoặc nguồn quản lý được chấp nhận.

Những dữ liệu đó là dấu hiệu để đối soát, không phải lúc nào cũng là quyết định cuối cùng.

Ví dụ:

- Người tạo khóa có thể chỉ thực hiện yêu cầu thay mặt một đội khác.
- Nhãn tên ứng dụng có thể đã cũ.
- Người thường dùng tài khoản có thể là nhà thầu hoặc đội hỗ trợ.
- Một principal không có log gần đây vẫn có thể phục vụ công việc theo chu kỳ dài.

### 5.2. Xác nhận đúng phạm vi và thẩm quyền

Cần đối chiếu credential với principal, môi trường, tài nguyên và mục đích. Sau đó kiểm tra owner ứng viên có thực sự chịu trách nhiệm trong phạm vi đó không.

Một đội vận hành môi trường thử nghiệm không tự trở thành owner của credential production chỉ vì tên giống nhau.

Không tin trường owner do người yêu cầu tự gửi nếu chưa đối chiếu nguồn thẩm quyền.

### 5.3. Chấp nhận trách nhiệm

Owner được chỉ định cần biết những gì đang nhận:

- Mục đích và mức ảnh hưởng.
- Những consumer đã biết cùng khoảng trống kiểm kê.
- Các vấn đề rotation hoặc thu hồi đang tồn tại.
- Ngoại lệ và công việc chưa hoàn tất.
- Điều kiện nhận việc và escalation.

Lưu bằng chứng chỉ định và chấp nhận. Một ô tên được điền trong danh sách không tự chứng minh việc chuyển giao đã hoàn tất.

### 5.4. Xác minh khả năng vận hành

Có thể xác minh bằng việc phân giải đúng đầu mối, giao được một công việc review hoặc xác nhận được quy trình xử lý. Không cần tiết lộ bí mật cho owner để chứng minh họ đã nhận trách nhiệm.

Nếu owner không có khả năng điều phối công việc hoặc không có phạm vi thẩm quyền phù hợp, cần sửa mô hình trách nhiệm thay vì chỉ đổi tên trường.

## 6. Ownership trong vòng đời credential

~~~mermaid
flowchart TD
    Need[Nhu cầu và chủ thể được xác nhận] --> Assign[Chỉ định và chấp nhận owner]
    Assign --> Manage[Đưa vào quản lý PAM]
    Manage --> Use[Sử dụng theo chính sách]
    Use --> Review[Review nhu cầu, quyền và phụ thuộc]
    Review --> Rotate[Luân chuyển và xác minh]
    Rotate --> Use
    Review --> Transfer[Chuyển giao ownership]
    Transfer --> Use
    Review --> Retire[Thu hồi và kết thúc]
    Manage --> Gap[Phát hiện khoảng trống]
    Gap --> Resolve[Điều phối xử lý và ghi bằng chứng]
    Resolve --> Review
~~~

Các trạng thái này mang tính khái niệm. Hệ thống thực tế cần quy tắc chuyển trạng thái và bằng chứng tương ứng.

### Khi tạo hoặc onboarding

Cần xác lập owner cho đối tượng trước khi coi việc quản lý đã đầy đủ. Với credential được phát hiện sau khi đã tồn tại, có thể cần một trạng thái tạm thời để xử lý khoảng trống.

Không hợp thức hóa trạng thái đầy đủ bằng cách mặc định gán mọi credential chưa rõ cho đội PAM.

### Khi rotation tạo phiên bản mới

Trách nhiệm thường tiếp tục theo credential hoặc principal được quản lý, nhưng cần giữ liên kết phiên bản và những thay đổi consumer.

Không để mỗi lần rotation tạo một bản ghi mới mất owner, cũng không tự sao chép một owner đã hết hiệu lực mà không có kiểm tra phù hợp.

### Khi kết thúc

Owner xác nhận nhu cầu kết thúc trong phạm vi của mình; đội được giao thực hiện thu hồi và xác minh. Lịch sử ownership và quyết định cần tiếp tục giải thích được những hành động đã xảy ra.

Xóa metadata trong vault không đồng nghĩa thu hồi credential hoặc tài khoản ở đích.

## 7. Trách nhiệm đối với least privilege, JIT và JEA

Credential owner phải phối hợp để giải thích vì sao credential cần tồn tại và cách sử dụng có phù hợp nhu cầu hay không.

Những câu hỏi review hữu ích:

1. Principal đang có những khả năng nào?
2. Credential này được phân phối cho những chủ thể nào?
3. Có cần quyền hoặc bí mật thường trực không?
4. Có thể tách nhiệm vụ hoặc dùng danh tính riêng không?
5. Có thể cấp theo thời gian hoặc giới hạn tác vụ không?
6. Ai có thể sửa điều kiện cấp hoặc tự tạo đường quyền mới?
7. Bằng chứng nào cho thấy phạm vi hiện tại còn phù hợp?

Owner không tự quyết định mọi quyền trên tài nguyên. Những thay đổi cần được resource owner hoặc bên có thẩm quyền tương ứng chấp nhận.

### Secret ngắn hạn vẫn cần owner

Credential được cấp ngắn hạn không làm mất nhu cầu xác định trách nhiệm. Cần có owner cho cơ chế cấp, policy, principal và workload sử dụng.

Nếu hệ thống dùng danh tính workload thay cho mật khẩu tĩnh, vẫn phải quản lý quan hệ tin cậy, bên có thể nhận danh tính, quyền ở đích và vòng đời.

### Hết hạn chưa chắc đã hết khả năng truy cập

Một lease hoặc yêu cầu JIT hết hạn trong PAM không tự chứng minh credential hoặc phiên tại đích đã mất tác dụng.

Owner cần biết cam kết thu hồi thực tế của cơ chế đang dùng và ai xác minh kết quả khi có lỗi.

## 8. Ownership và danh sách consumer

Một credential của tài khoản dịch vụ có thể được dùng bởi API, worker, job theo lịch và công cụ vận hành. Danh sách consumer là một phần quan trọng của trách nhiệm vòng đời.

Với mỗi consumer, nên biết:

- Chủ sở hữu hoặc đầu mối kỹ thuật.
- Môi trường chạy và mục đích sử dụng.
- Cách nhận credential.
- Thời điểm nạp lại và cơ chế cache.
- Kết nối dài hạn hoặc connection pool.
- Lịch chạy và những tác vụ hiếm.
- Cách chuyển đổi và bằng chứng kiểm tra.

### Đừng biến quan sát thành cam kết đầy đủ

Không thấy một consumer trong log không chứng minh nó không tồn tại. Dữ liệu có thể thiếu hoặc cửa sổ quan sát không bao phủ chu kỳ công việc.

Nên phân biệt:

| Trạng thái | Ý nghĩa |
| --- | --- |
| Đã xác nhận | Consumer owner và bằng chứng phù hợp xác nhận quan hệ |
| Có dấu hiệu | Có tham chiếu hoặc hoạt động cần đối soát |
| Chưa rõ | Chưa đủ dữ liệu để kết luận |
| Đã kết thúc | Có quyết định và bằng chứng xử lý trong phạm vi |

Credential owner điều phối tổng thể; từng consumer owner xác nhận phần mình. Không đóng công việc chuyển đổi chỉ vì ứng dụng chính đã hoạt động.

## 9. Hợp đồng vận hành cho rotation và thu hồi

Một sự kiện vault báo thành công chưa chứng minh toàn bộ vòng đời đã được xử lý.

| Phần việc | Trách nhiệm cần làm rõ |
| --- | --- |
| Xác nhận nhu cầu thay đổi | Ai giải thích lý do và phạm vi? |
| Kiểm kê phụ thuộc | Ai tổng hợp và ai xác nhận từng consumer? |
| Thực hiện thay đổi | Ai có quyền thao tác tại nguồn có thẩm quyền? |
| Cập nhật bên sử dụng | Ai chuyển cấu hình, nạp lại hoặc triển khai? |
| Xác minh | Ai kiểm tra kết nối mới, tác vụ hợp lệ và hiệu lực credential cũ? |
| Xử lý lỗi | Ai quyết định dừng, đối soát hoặc phục hồi? |
| Đóng công việc | Ai xác nhận tiêu chí và ghi những phần còn lại? |

Credential owner phải bảo đảm các trách nhiệm này không bị bỏ trống. Điều đó không có nghĩa owner phải được cấp quyền trực tiếp để thực hiện tất cả thao tác.

### Trạng thái chưa xác định cần có người giữ việc

Nếu mất kết nối sau khi yêu cầu đổi mật khẩu, chưa biết đích đã đổi hay chưa, công việc vẫn cần người chịu trách nhiệm điều phối đối soát.

Không chuyển trạng thái thành hoàn tất chỉ vì đã gửi thông báo cho owner. Cũng không retry vô hạn nếu có nguy cơ làm lệch trạng thái hoặc khóa tài khoản.

### Thu hồi phải xét nhiều lớp

Cần phân biệt:

- Quyền lấy credential mới từ vault.
- Credential đã được gửi hoặc sao chép.
- Phiên và kết nối đang tồn tại.
- Credential hoặc principal khác được tạo từ quyền ban đầu.

Chặn lớp đầu không tự xử lý mọi lớp sau. Ownership phải gắn với kết quả cần đạt và người phối hợp ở hệ thống đích.

## 10. Chuyển giao ownership

Chuyển giao là thay đổi trách nhiệm có kiểm soát, không chỉ sửa một nhãn.

### Quy trình khái niệm

1. Xác định lý do, phạm vi và thời điểm hiệu lực.
2. Xác minh bên nhận có thẩm quyền và năng lực phù hợp.
3. Bàn giao principal, consumer, policy và các việc đang mở.
4. Ghi nhận chấp nhận trách nhiệm.
5. Cập nhật nguồn ánh xạ và workflow liên quan.
6. Review quyền của bên cũ và bên mới.
7. Xác minh đường liên hệ, nhận cảnh báo và escalation.
8. Lưu lịch sử cùng phần chưa hoàn tất.

Nếu chưa có bên nhận, cần ghi khoảng trống và dùng đường điều phối tạm thời. Không tiếp tục hiển thị một người đã rời tổ chức là owner hợp lệ chỉ để danh sách trông đầy đủ.

### Ownership thay đổi không tự thu hồi quyền

Bên cũ có thể vẫn:

- Nằm trong nhóm được đọc bí mật.
- Có quyền mở phiên.
- Giữ bản sao credential.
- Có token hoặc phiên đang tồn tại.
- Sửa được pipeline, workload hoặc policy liên quan.

Những khả năng này phải được review riêng theo cơ chế hệ thống.

### Có luôn phải đổi credential không?

Cần dựa trên đường tiếp cận và mục tiêu thu hồi. Nếu bên cũ biết bí mật dùng chung và không còn được phép sử dụng, chỉ bỏ tên owner không loại bỏ khả năng dùng bản sao; cần xử lý credential ở đích phù hợp.

Nếu thay đổi chỉ là trách nhiệm metadata và không tạo thay đổi về những bên được tiếp cận bí mật, không nên mặc định một rotation khẩn cấp mà chưa đánh giá nhu cầu và tác động.

Trong trường hợp nghi ngờ lộ credential, phải xử lý theo quy trình sự cố, không dùng chuyển giao hành chính làm biện pháp thay thế.

## 11. Thay đổi nhân sự, dịch vụ và cơ cấu tổ chức

### Người tạo credential nghỉ việc

Không tự động kết luận mọi credential do người đó tạo đều phải bị xóa ngay. Có thể đó là credential của dịch vụ đang hoạt động.

Cần xác định quyền cá nhân phải thu hồi, owner thực sự của dịch vụ và nhu cầu credential. Nếu tồn tại rủi ro khẩn cấp, người có thẩm quyền có thể quyết định containment theo quy trình mà không chờ hoàn tất việc tìm owner.

### Dịch vụ chuyển đội

Cần chuyển cả trách nhiệm và những liên kết vận hành: consumer, thông báo, policy, review, rotation, ngoại lệ và đường phục hồi.

Một bản ghi owner mới không bảo đảm cảnh báo đã được chuyển đúng nơi hoặc bên nhận đã biết một job theo lịch dài.

### Dịch vụ tách hoặc hợp nhất

Credential dùng chung giữa nhiều dịch vụ có thể cần tách theo principal hoặc mục đích để giảm phạm vi ảnh hưởng.

Nếu giữ dùng chung trong giai đoạn chuyển tiếp, phải có đầu mối điều phối, trách nhiệm từng consumer và thời hạn xem xét phù hợp. Không mặc định chuyển toàn bộ trách nhiệm sang đội đang giữ vault.

### Danh tính ngắn hạn hoặc tự động

Credential được tạo bởi máy vẫn cần một owner tổ chức cho cơ chế tạo và workload. Tên của một job hoặc tài khoản tự động không tự thay thế trách nhiệm con người trong quản trị.

## 12. Xử lý credential chưa có owner hợp lệ

Cần phân biệt các tình huống:

| Tình huống | Ý nghĩa |
| --- | --- |
| Chưa có owner | Chưa xác định ai chịu trách nhiệm |
| Owner ứng viên | Có dấu hiệu nhưng chưa xác nhận |
| Owner hết hiệu lực | Người hoặc nhóm không còn giữ trách nhiệm phù hợp |
| Owner không liên hệ được | Cần kiểm tra cơ chế nhận việc và escalation |
| Owner tranh chấp | Nhiều bên không thống nhất về phạm vi |
| Credential không còn nhu cầu | Một kết luận khác, cần bằng chứng riêng |

Credential chưa có owner không tự đồng nghĩa credential đang bị lộ hoặc không còn cần thiết. Tuy nhiên, đó là một khoảng trống kiểm soát cần xử lý.

### Luồng xử lý

1. Ghi định danh, phạm vi và bằng chứng quan sát.
2. Đánh giá khả năng gây tác động và đường tiếp cận.
3. Chỉ định đầu mối điều phối tạm thời có phạm vi rõ.
4. Tìm owner ứng viên từ các nguồn được chấp nhận.
5. Xác nhận nhu cầu và consumer.
6. Chọn giữ có kiểm soát, chuyển giao, thu hẹp, tách hoặc thu hồi.
7. Xác minh thay đổi và kết thúc trách nhiệm tạm thời.

Thời hạn xử lý cần theo mức rủi ro và chính sách thực tế; không có một số ngày chung phù hợp mọi hệ thống.

### Đầu mối tạm thời không phải owner vĩnh viễn

Người điều phối tạm thời có thể chịu trách nhiệm tìm owner, hạn chế phân phối mới và theo dõi việc mở. Họ không tự nhận quyền quyết định nghiệp vụ trên mọi tài nguyên.

Cần ghi thời hạn, phạm vi quyền và đường escalation. Không để một hàng đợi “unassigned” trở thành nơi cất credential đặc quyền không ai xem.

### Khi có dấu hiệu bị lạm dụng

Không đợi đủ thủ tục xác lập ownership mới bắt đầu ứng phó. Người có thẩm quyền theo quy trình sự cố có thể điều phối bảo toàn bằng chứng, hạn chế truy cập và xử lý credential hoặc phiên.

Sau đó vẫn phải giải quyết ownership để tránh khoảng trống tái diễn.

## 13. Ownership cho các credential đặc biệt

### 13.1. Credential quản lý credential khác

Tài khoản reset, tài khoản reconciliation, danh tính quản trị vault hoặc khóa bảo vệ kho có thể tác động đến nhiều bí mật.

Cần xác định riêng owner, người được sử dụng, phạm vi thao tác, review và đường phục hồi. Không bỏ qua chúng vì chúng là “tài khoản kỹ thuật của công cụ PAM”.

### 13.2. Khóa và chứng thư

Cần phân biệt owner của dịch vụ dùng khóa, đơn vị vận hành cơ chế phát hành và bên có thẩm quyền với quan hệ tin cậy tại đích.

Đổi hoặc thu hồi vật liệu ở nơi phát hành chưa tự chứng minh mọi đích đã ngừng chấp nhận hoặc mọi phiên đã kết thúc. Hành vi cụ thể phải được đưa vào hợp đồng vận hành.

### 13.3. Credential khẩn cấp

Ownership cần bao phủ mục đích phục hồi, điều kiện kích hoạt, cách phân phối được bảo vệ, bằng chứng và xử lý sau sử dụng.

Đường khẩn cấp phải được xem xét theo kịch bản mất phụ thuộc. Nếu muốn lấy credential phục hồi vault nhưng bắt buộc phải dùng chính vault đang hỏng, ownership cần phối hợp giải quyết phụ thuộc vòng đó.

### 13.4. Tài khoản cá nhân có đặc quyền

Danh tính cá nhân giúp truy vết, nhưng tổ chức vẫn cần trách nhiệm về quyền được cấp, tài nguyên và vòng đời khi người dùng chuyển vai trò.

Không coi “người dùng tự chịu trách nhiệm mật khẩu” là lý do bỏ review quyền, giám sát phiên hoặc thu hồi theo sự kiện.

## 14. Ví dụ xuyên suốt: credential của dịch vụ A

Một credential được tạo bởi kỹ sư triển khai cho tài khoản dịch vụ A. API A và một job báo cáo của đội B đang dùng cùng credential. Bản ghi vault còn ghi tên kỹ sư đã chuyển đội; rotation từng bị hoãn vì chưa biết lịch của job báo cáo.

### Phân tích

- Người tạo không còn là căn cứ đủ để giữ ownership hiện tại.
- Đội PAM đang lưu bí mật nhưng không tự biết nhu cầu của hai consumer.
- Đội A có thể là owner chính nếu được chỉ định và chấp nhận đúng phạm vi.
- Đội B cần chịu trách nhiệm phần consumer của mình.
- Quyền của tài khoản phải được resource owner xác nhận.
- Việc trì hoãn rotation cần hồ sơ và người chịu trách nhiệm, không chỉ một ghi chú cũ.

### Hướng xử lý

1. Đối soát đúng principal, credential và tài nguyên.
2. Chỉ định đầu mối điều phối trong khi xác nhận ownership.
3. Xác nhận đội A nhận trách nhiệm chính và đội B nhận phần consumer.
4. Kiểm kê cách nạp bí mật, cache và lịch chạy.
5. Đánh giá tách tài khoản cho job B để giảm dùng chung.
6. Lập kế hoạch rotation hoặc chuyển đổi phù hợp.
7. Xác minh kết nối mới và tác vụ của cả hai bên.
8. Review quyền và khả năng tiếp cận còn lại của kỹ sư cũ.
9. Lưu lịch sử, quyết định và công việc còn mở.

Nếu chưa tách được ngay, cần giữ rõ trạng thái dùng chung và kế hoạch xử lý. Không mô tả credential đã được tách chỉ vì có hai consumer owner trong hồ sơ.

### Khi hoàn tất

Có thể coi ownership đã được xác lập khi đầu mối đúng thẩm quyền đã nhận trách nhiệm, consumer liên quan được ghi nhận, workflow phân giải đúng người và những khoảng trống được theo dõi.

Điều đó chưa tự chứng minh rotation, thu hẹp quyền hay thu hồi bên cũ đã hoàn tất. Các kết quả đó có tiêu chí riêng.

## 15. Hồ sơ ownership minh họa

Ví dụ sau là **mô tả dữ liệu quản trị, không phải cấu hình chạy trực tiếp của một sản phẩm**. Không điền giá trị bí mật vào hồ sơ.

~~~yaml
credential_record:
  reference: credential-service-a-example
  principal_reference: service-a-runtime
  authentication_authority: production-platform-a
  purpose: application-runtime
  environment: production

ownership:
  accountable_role: service-owner
  accountable_group: application-a-operations
  current_contact_reference: protected-role-mapping
  status: accepted
  authority_reference: approved-service-assignment
  acceptance_reference: protected-handover-record
  review_policy_reference: credential-ownership-review

related_responsibilities:
  resource_owner_reference: production-data-owner
  pam_custodian_reference: pam-operations
  consumers:
    - consumer_reference: service-a-api
      owner_reference: application-a-operations
      confirmation: verified
    - consumer_reference: reporting-job-b
      owner_reference: reporting-operations
      confirmation: verified

lifecycle:
  rotation_policy_reference: service-a-rotation-plan
  revocation_runbook_reference: approved-revocation-process
  escalation_reference: service-a-responsibility-escalation

evidence:
  secret_value_in_record: false
  open_items:
    - evaluate-separate-identity-for-reporting-job
~~~

Trạng thái “accepted” mô tả việc nhận ownership theo mô hình minh họa. Nó không có nghĩa mọi vấn đề trong danh sách việc mở đã được xử lý.

Tham chiếu đến người liên hệ và thẩm quyền phải phân giải được tại thời điểm sử dụng. Không nên để hồ sơ tiếp tục chỉ về một nhóm đã bị giải thể.

## 16. Bằng chứng, audit và phân quyền metadata

Một quyết định ownership cần giải thích được:

- Ai chỉ định, ai chấp nhận và theo thẩm quyền nào.
- Đối tượng và phạm vi nào được bàn giao.
- Những consumer, ngoại lệ và việc mở tại thời điểm đó.
- Khi nào có hiệu lực.
- Những quyền hoặc workflow liên quan đã thay đổi.
- Ai thực hiện và kết quả xác minh.

### Metadata cũng có thể tạo đường quyền

Nếu sửa owner làm thay đổi người phê duyệt hoặc người được đọc bí mật, quyền sửa trường đó là một khả năng nhạy cảm.

Cần kiểm soát người được sửa, xác thực nguồn, ghi audit và kiểm tra tác động. Không cho phép người yêu cầu tự chọn owner để nhận quyền hoặc tự duyệt.

### Giữ lịch sử theo thời điểm

Khi điều tra một lần truy xuất cũ, cần biết owner và cơ chế ủy quyền tại thời điểm sự kiện. Owner hiện tại không nhất thiết chịu trách nhiệm cho mọi quyết định trong quá khứ.

Lịch sử phải gắn với định danh đủ ổn định và nguồn thay đổi. Không chỉ ghi một tên hiển thị có thể bị đổi hoặc tái sử dụng.

### Không dùng audit để sao chép bí mật

Bằng chứng nên dùng ID credential, phiên bản, mã thay đổi và kết quả. Không ghi mật khẩu, token, khóa riêng hoặc vật liệu phục hồi vào biên bản bàn giao.

## 17. Review và đo chất lượng ownership

Review cần được thực hiện theo lịch phù hợp và theo sự kiện, chẳng hạn đổi chủ dịch vụ, chuyển đội, kết thúc dự án, thêm consumer, sự cố hoặc thay mô hình xác thực.

### Câu hỏi review

1. Owner còn đúng phạm vi và có thẩm quyền không?
2. Nhóm và đầu mối liên hệ còn hoạt động không?
3. Danh sách consumer có thay đổi không?
4. Mục đích và quyền của principal còn phù hợp không?
5. Kế hoạch rotation, thu hồi và phục hồi có thực hiện được không?
6. Ngoại lệ có còn hiệu lực và có người theo dõi không?
7. Workflow có phân giải đúng người khi cần quyết định không?

### Định nghĩa mẫu số

Có thể đo tỷ lệ credential trong phạm vi có owner đã xác nhận và còn hiệu lực. Cần định nghĩa đơn vị là bản ghi credential logic được quản lý, không trộn với số principal, phiên bản hay consumer.

Ví dụ, có 24 bản ghi credential trong phạm vi:

- 20 bản ghi có owner đã xác nhận và còn hiệu lực.
- 2 bản ghi mới có owner ứng viên.
- 2 bản ghi chưa xác định owner.

Tỷ lệ có owner đã xác nhận là **20/24, khoảng 83,3%**. Không tính owner ứng viên thành đã hoàn tất.

Tỷ lệ này đo độ bao phủ trách nhiệm của tập đã định nghĩa. Nó không tự chứng minh quyền đã tối thiểu, credential đã rotation thành công hoặc toàn bộ hạ tầng đã được kiểm kê.

### Những chỉ số bổ sung

| Chỉ số | Mục đích |
| --- | --- |
| Owner hết hiệu lực hoặc không liên hệ được | Phát hiện khoảng trống hiện tại |
| Chuyển giao chờ chấp nhận | Theo dõi trách nhiệm chưa hoàn tất |
| Consumer chưa xác nhận | Nhận diện rủi ro thay đổi credential |
| Credential dùng chung nhiều dịch vụ | Ưu tiên đánh giá tách nhiệm vụ |
| Ngoại lệ quá hạn | Theo dõi công việc cần quyết định lại |
| Công việc vòng đời không có người nhận | Đo hiệu quả thực tế của ownership |
| Sai ánh xạ người phê duyệt | Phát hiện rủi ro quyền và workflow |

Số ô owner được điền không đủ. Cần kiểm tra tính hợp lệ và khả năng nhận trách nhiệm.

## 18. Những lỗi thường gặp

| Lỗi | Hệ quả | Hướng xử lý |
| --- | --- | --- |
| Mặc định người tạo là owner | Ownership có thể sai hoặc hết hiệu lực | Xác nhận vai trò và chấp nhận trách nhiệm |
| Mặc định đội vault sở hữu mọi bí mật | Không rõ nhu cầu và phụ thuộc | Tách custodian khỏi trách nhiệm dịch vụ |
| Gán owner là được đọc bí mật | Tạo quyền ngoài ý định | Quản lý trách nhiệm và phân quyền riêng |
| Ghi nhiều đội nhưng không có đầu mối | Không ai điều phối khi có lỗi | Chỉ định trách nhiệm chính và phần việc |
| Chuyển owner nhưng giữ quyền bên cũ | Khả năng truy cập vẫn tồn tại | Review nhóm, credential, phiên và đường gián tiếp |
| Xóa credential vì người tạo nghỉ việc | Có thể làm hỏng dịch vụ | Xác minh nhu cầu và xử lý theo mức rủi ro |
| Không thấy log nên kết luận không dùng | Có thể bỏ sót job hoặc nguồn dữ liệu | Kết hợp consumer, lịch công việc và bằng chứng |
| Có owner là báo rotation hoàn tất | Nhầm trách nhiệm với kết quả kỹ thuật | Xác minh từng tiêu chí vòng đời |
| Dùng đầu mối tạm thời vô thời hạn | Khoảng trống trở thành trạng thái mặc định | Có thời hạn, escalation và điều kiện kết thúc |
| Bàn giao bằng cách gửi bí mật | Tạo bản sao ngoài kiểm soát | Bàn giao tham chiếu, quyền và quy trình |

## 19. Bài tập tự đánh giá

Một khóa truy cập đặc quyền được ghi tên người tạo làm owner. Người này đã chuyển đội. Khóa đang nằm trong vault, được API và một job theo chu kỳ dài sử dụng. Đội PAM cho rằng chỉ cần đổi trường owner sang tên đội vận hành vault rồi đóng việc. Đội ứng dụng đề nghị xóa khóa vì một khoảng log gần đây không thấy job dùng.

Hãy trả lời:

1. Những vai trò nào đang bị gộp nhầm?
2. Cần bằng chứng gì để xác lập owner mới?
3. Vì sao không thấy log chưa đủ để kết luận job không còn cần khóa?
4. Đổi owner có tự thu hồi quyền của người cũ không?
5. Khi nào có thể coi ownership đã được xử lý?
6. Nếu nghi khóa bị lộ, có phải chờ tìm đủ owner mới ứng phó không?

### Gợi ý phân tích

**Vai trò:** người tạo, custodian vault, owner của credential và owner của từng consumer là những trách nhiệm cần đối soát.

**Owner mới:** cần phạm vi, nguồn thẩm quyền, chấp nhận trách nhiệm, khả năng nhận việc và thông tin phụ thuộc.

**Dữ liệu sử dụng:** cửa sổ quan sát có thể không bao phủ chu kỳ job; log cũng có thể thiếu. Cần lịch và xác nhận consumer owner.

**Quyền người cũ:** metadata thay đổi không tự xóa nhóm, bản sao credential, phiên hoặc khả năng sửa workload.

**Hoàn tất ownership:** đầu mối hợp lệ đã nhận trách nhiệm, workflow hoạt động và phần chưa rõ được theo dõi. Rotation hoặc thu hồi có kết quả nghiệm thu riêng.

**Sự cố:** hành động khẩn cấp được quyết định theo thẩm quyền ứng phó, đồng thời bảo toàn bằng chứng và tiếp tục xử lý khoảng trống ownership.

## 20. Những điểm cần ghi nhớ

- Credential ownership là trách nhiệm có phạm vi, thẩm quyền, đầu mối và bằng chứng; không chỉ là một trường tên.
- Owner, người tạo, người sử dụng và custodian vault không tự là cùng một vai trò.
- Cần ánh xạ credential với principal, tài nguyên, nguồn xác thực và consumer.
- Quyền đọc bí mật, sửa policy và phê duyệt phải được kiểm soát riêng với ownership.
- Chuyển giao phải xử lý cả trách nhiệm, workflow, quyền cũ và những bản sao hoặc phiên liên quan.
- Credential chưa rõ owner cần luồng điều phối có thời hạn; sự cố không nên chờ thủ tục ownership vô thời hạn.
- Ownership tốt phải dẫn đến quyết định và kết quả vòng đời được xác minh, không chỉ làm danh sách đầy đủ hơn.
