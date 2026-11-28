# Degraded mode trong hệ thống PAM có tính sẵn sàng cao

## 1. Degraded mode là gì?

Degraded mode là chế độ vận hành suy giảm có chủ đích: khi một số thành phần hoặc dịch vụ phụ thuộc gặp sự cố, hệ thống quản lý truy cập đặc quyền (Privileged Access Management — PAM) chỉ tiếp tục những hoạt động vẫn đáp ứng được các điều kiện an toàn đã xác định. Phạm vi chức năng, số lượng phiên, thời gian truy cập hoặc đối tượng được phục vụ có thể giảm xuống.

Một cổng PAM vẫn trả về trang đăng nhập chưa chứng minh rằng hệ thống có thể cấp quyền an toàn. Đăng nhập có thể hoạt động trong khi dịch vụ phê duyệt mất kết nối, vault mất quorum hoặc nơi lưu bản ghi phiên không còn dung lượng. Ngược lại, dịch vụ cấp quyền có thể dừng nhưng một số phiên đang chạy vẫn được kiểm soát và ghi nhận đầy đủ.

Vì vậy, degraded mode phải được mô tả theo **khả năng cụ thể**, không chỉ bằng một nhãn “đang hoạt động” cho toàn hệ thống:

- Còn xác minh được danh tính người yêu cầu hay không?
- Còn đánh giá được quyền và trạng thái phê duyệt cho đúng tài nguyên hay không?
- Còn cấp và thu hồi được credential hay không?
- Còn ghi bền vững được bằng chứng bắt buộc hay không?
- Còn kiểm soát được phiên truy cập đang tồn tại hay không?

Trong module PAM, mục tiêu của chế độ này là duy trì những hoạt động quản trị cần thiết mà vẫn giữ được least privilege, giới hạn JIT/JEA, bảo vệ credential và khả năng truy vết. Hệ thống không được tự biến sự cố hạ tầng thành lý do mở rộng quyền.

### Ví dụ mở đầu

Một tổ chức sử dụng PAM để quản trị máy chủ thanh toán. Khi hệ thống nhận log tập trung ngừng hoạt động, các gateway vẫn có vùng đệm audit bền vững, còn dung lượng và còn khả năng ghi bản ghi phiên. Theo chính sách đã duyệt, gateway có thể tiếp tục một tập phiên giới hạn trong thời gian ngắn.

Nếu sau đó vùng đệm gần đầy, gateway giảm số phiên mới được nhận. Khi không thể bảo đảm lưu bằng chứng cho phiên tiếp theo, nó từ chối cấp phiên đó. Việc hệ thống đích vẫn chạy bình thường không làm mất yêu cầu audit.

Đây là degraded mode có kiểm soát: quyết định tiếp tục hay dừng phụ thuộc vào những bảo đảm còn giữ được, cùng ngân sách và thời hạn đã xác định.

## 2. Phân biệt degraded mode với các cơ chế liên quan

| Khái niệm | Vai trò chính | Ví dụ trong PAM |
|---|---|---|
| High availability | Giảm gián đoạn khi một thành phần hỏng | Gateway khác nhận phiên mới khi một gateway ngừng hoạt động |
| Failover | Chuyển vai trò hoặc lưu lượng sang thành phần thay thế | Chuyển yêu cầu tới vault node hợp lệ còn phục vụ |
| Degraded mode | Thu hẹp chức năng theo những bảo đảm còn tồn tại | Tiếp tục phiên hiện hữu có lease hợp lệ, tạm dừng cấp quyền mới |
| Disaster recovery | Khôi phục khả năng phục vụ sau sự cố lớn | Khôi phục dịch vụ PAM tại địa điểm dự phòng |
| Break-glass | Cấp đường truy cập khẩn cấp theo quy trình riêng | Người ứng cứu được ủy quyền dùng credential khẩn cấp có kiểm soát |

Failover có thể diễn ra mà người dùng không nhận thấy suy giảm đáng kể. Degraded mode vẫn có thể tồn tại sau failover nếu thành phần mới chưa kết nối được với dịch vụ danh tính, nơi lưu audit hoặc hệ thống đích.

Break-glass cũng không đồng nghĩa với “PAM gặp lỗi thì cho phép đăng nhập trực tiếp”. Đó phải là một luồng được thiết kế, phê duyệt và giám sát riêng, với danh tính, phạm vi, thời hạn và trách nhiệm rõ ràng. Nếu đường khẩn cấp phụ thuộc hoàn toàn vào chính thành phần đã hỏng, tổ chức có thể không còn khả năng sử dụng nó khi cần.

## 3. Bắt đầu bằng bản đồ phụ thuộc và bất biến an toàn

Một triển khai PAM thường có nhiều phụ thuộc: nhà cung cấp danh tính, MFA, bộ đánh giá chính sách, hệ thống phê duyệt, vault, cơ chế lease, session broker, kho bản ghi, nguồn thời gian và hệ thống nhận sự kiện.

Không nên chỉ hỏi “thành phần nào đang đỏ?”. Cần hỏi thêm: “sự cố này làm mất bảo đảm nào của từng hoạt động?”.

Ví dụ, mất kết nối tới kho tìm kiếm audit có thể chỉ làm chậm tra cứu nếu bằng chứng gốc vẫn được ghi an toàn. Mất cơ chế ghi audit tại gateway lại ảnh hưởng trực tiếp tới việc chấp nhận phiên mới. Hai trường hợp đều liên quan tới audit nhưng hậu quả khác nhau.

### Các bất biến cần bảo vệ

Một thiết kế degraded mode nên quy định rõ những điều kiện không được tự ý bỏ qua:

1. **Danh tính có thể quy trách nhiệm.** Yêu cầu đặc quyền phải gắn với một chủ thể đã được xác minh bằng cơ chế được chấp nhận cho luồng đó.
2. **Quyền không vượt phê duyệt.** Người dùng, tài nguyên, hành động và thời hạn phải nằm trong phạm vi được phép.
3. **Credential còn hiệu lực theo mô hình quản lý của nó.** Không cấp lại credential đã hết hạn, bị thu hồi hoặc có trạng thái không thể xác định trong tình huống chính sách yêu cầu xác minh.
4. **Bằng chứng bắt buộc có nơi lưu bền vững.** Chưa chuyển được lên hệ thống trung tâm khác với chưa ghi được bằng chứng.
5. **Không có hai chủ thể cùng thực hiện thao tác ghi xung đột.** Hoạt động cấp, xoay vòng và cập nhật bí mật phải tuân thủ cơ chế điều phối của hệ thống.
6. **Chế độ suy giảm tự hết hạn.** Mọi ngoại lệ có thời hạn, điều kiện dừng và người chịu trách nhiệm.
7. **Có đường thoát và phục hồi.** Hệ thống biết phải làm gì với phiên, credential và bằng chứng phát sinh trong thời gian sự cố.

Các bất biến phải phù hợp với thiết kế thực tế. Ví dụ, việc tạm thời không truy vấn được nguồn thu hồi quyền là chấp nhận được hay không phụ thuộc vào loại truy cập, thời hạn credential và chính sách của tổ chức. Đây là quyết định cần được xác định trước, không phải quyết định tùy ý của gateway lúc xảy ra lỗi.

## 4. Tách quyết định theo từng loại hoạt động

Một công tắc chung “allow on error” quá thô cho PAM. Nên đánh giá riêng ít nhất các loại hoạt động sau:

- Xác thực mới và tái xác thực.
- Cấp phiên mới.
- Tiếp tục phiên đang chạy.
- Gia hạn phiên hoặc lease.
- Cấp credential cho người hoặc workload.
- Tạo mới, thay đổi hoặc phê duyệt quyền.
- Xoay vòng credential.
- Thu hồi quyền và chấm dứt phiên.
- Lưu, chuyển tiếp và tra cứu bằng chứng.

Một phiên đã được cấp hợp lệ có thể được tiếp tục trong phạm vi lease ban đầu, trong khi việc mở phiên mới bị từ chối. Tuy nhiên, **tiếp tục phiên không bao gồm tự động gia hạn**. Nếu việc gia hạn cần một quyết định mới từ dịch vụ đang mất kết nối, gateway không được giả định rằng phê duyệt cũ vẫn bao phủ phần thời gian bổ sung.

Tương tự, việc cho phép đọc một bí mật đã được cấp trước đó không có nghĩa là cho phép tạo thêm tài khoản quản trị hoặc thay đổi danh sách người được nhận bí mật.

### Ma trận quyết định minh họa

Bảng sau là một thiết kế tham khảo, không phải hành vi mặc định của mọi sản phẩm PAM.

| Tình trạng | Phiên mới | Phiên hiện hữu | Thao tác quản lý credential |
|---|---|---|---|
| Chỉ mất hệ thống tra cứu log; nguồn audit gốc còn ghi tốt | Có thể tiếp tục theo chính sách | Tiếp tục nếu còn đủ điều kiện | Đánh giá theo các phụ thuộc khác |
| Mất hệ thống nhận audit trung tâm; local spool còn an toàn | Có thể cấp giới hạn trong ngân sách đã duyệt | Theo dõi dung lượng và thời hạn | Chỉ thực hiện nếu có audit bền vững và điều phối hợp lệ |
| Không thể ghi audit bắt buộc ở bất kỳ nơi được chấp nhận nào | Từ chối | Áp dụng quy tắc dừng phiên của loại tài nguyên | Từ chối thao tác đòi hỏi bằng chứng đó |
| Mất dịch vụ phê duyệt | Chỉ cân nhắc grant đã cấp, còn hiệu lực và dùng được cho yêu cầu này | Không mở rộng grant cũ | Tạm dừng thay đổi cần phê duyệt mới |
| Vault không có điều kiện phục vụ an toàn | Từ chối nếu cần lấy credential mới | Không tự suy rằng phiên cũ đã bị đóng | Không ép ghi hoặc xoay vòng từ phía không có thẩm quyền |
| Không xác định được tính hợp lệ của quyền theo chính sách | Từ chối cấp mới | Đánh giá yêu cầu tái kiểm tra và khả năng chấm dứt | Không dùng dữ liệu không đủ tin cậy để mở rộng quyền |

Điểm quan trọng là mỗi ô trong ma trận phải có chủ sở hữu, điều kiện đo được và cách thực thi. “Tiếp tục nếu cần” không phải một chính sách có thể kiểm chứng.

## 5. Fail-closed và truy cập giới hạn có điều kiện

Fail-closed nghĩa là từ chối một hoạt động khi hệ thống không chứng minh được các điều kiện bắt buộc để cho phép hoạt động đó. Điều này không nhất thiết có nghĩa là tắt ngay mọi thành phần hoặc cắt tất cả phiên khi bất kỳ phụ thuộc nào lỗi.

Ví dụ:

- Không xác minh được quyền nhận credential mới: từ chối cấp credential.
- Không tải được giao diện báo cáo nhưng vẫn ghi được audit: có thể tiếp tục các hoạt động không phụ thuộc vào giao diện đó.
- Không ghi được bản ghi phiên bắt buộc: không nhận thêm phiên cần bản ghi.
- Mất kết nối tới nguồn chính sách: chỉ cân nhắc chính sách cục bộ nếu cơ chế đó đã được thiết kế, xác thực, giới hạn thời gian và được tổ chức chấp nhận.

Cần phân biệt **tiếp tục một quyền đã cấp trong giới hạn được duyệt** với **tự phê duyệt một quyền mới do không liên lạc được với hệ thống trung tâm**.

Trong một số môi trường có yêu cầu vận hành đặc biệt, tổ chức có thể xác định ngoại lệ cho một số tình huống. Ngoại lệ đó vẫn cần định danh người chịu trách nhiệm, điều kiện kích hoạt, phạm vi tài nguyên, giới hạn hành động, thời hạn và bằng chứng thay thế. Không biến ngoại lệ thành đường truy cập thường trực.

## 6. Các kiểu sự cố và cách suy giảm phù hợp

### 6.1. Mất IdP hoặc MFA

Khi nhà cung cấp danh tính hoặc MFA mất kết nối, cổng PAM không nên tự bỏ bước xác minh vốn bắt buộc cho lần truy cập mới.

Một số hệ thống có thể hỗ trợ cơ chế xác minh cục bộ hoặc bằng chứng xác thực có thể kiểm tra độc lập. Nếu sử dụng, phải xác định rõ:

- Cơ chế đó xác minh được điều gì và không xác minh được điều gì.
- Thời điểm xác thực, thời điểm hết hạn và mức bảo đảm được chấp nhận.
- Khả năng phát hiện tài khoản đã bị khóa hoặc quyền đã bị thu hồi.
- Việc bằng chứng có được ràng buộc với đúng người, thiết bị, dịch vụ và yêu cầu hay không.
- Giới hạn trước rủi ro phát lại, đánh cắp hoặc sử dụng ngoài ngữ cảnh.

Một token còn thời hạn không tự động chứng minh rằng chủ thể vẫn còn mọi quyền ban đầu. Xác thực danh tính và ủy quyền cho một hành động là hai điều kiện cần đánh giá riêng.

Với phiên đang chạy, cần xác định liệu chính sách yêu cầu tái xác thực vào thời điểm nào. Nếu lần tái xác thực bắt buộc không thực hiện được, hệ thống phải áp dụng quy tắc hết hạn hoặc chấm dứt đã thiết kế.

### 6.2. Mất dịch vụ chính sách hoặc phê duyệt

Nếu dịch vụ chính sách không truy cập được, không chuyển từ “không xác định” sang “cho phép”.

Một bản chính sách đã được xác thực và lưu cục bộ có thể hỗ trợ một tập quyết định hữu hạn nếu thiết kế cho phép. Nhưng bản chính sách và grant là hai thứ khác nhau: chính sách nói cách đánh giá, còn grant nói quyền nào đã được cấp cho chủ thể cụ thể.

Một grant dùng trong degraded mode nên có tối thiểu:

- Định danh grant và chủ thể nhận.
- Tài nguyên hoặc tập tài nguyên chính xác.
- Hành động được phép; với JEA, có thể là tập lệnh hoặc endpoint quản trị giới hạn.
- Thời điểm bắt đầu, hết hạn và điều kiện sử dụng.
- Tham chiếu phê duyệt và phiên bản chính sách.
- Các ràng buộc cần thiết như thiết bị, phiên, số lần dùng hoặc nơi phát hành.

Nếu grant chỉ dùng một lần nhưng nhiều gateway không đồng bộ được trạng thái đã dùng, việc mỗi gateway tự chấp nhận có thể gây sử dụng lặp. Phải có cơ chế chống lặp phù hợp hoặc từ chối luồng đó trong phân vùng mạng.

### 6.3. Mất quorum hoặc phân vùng mạng tại vault

Không phải mọi vault đều có cùng kiến trúc, nhưng nguyên tắc chung là không cho một thành phần tự nhận quyền ghi khi nó không còn điều kiện hợp lệ theo cơ chế điều phối của hệ thống.

Trong phân vùng mạng, hai phía có thể nhìn thấy trạng thái khác nhau. Nếu cả hai phía cùng xoay credential cho một tài khoản, hệ thống đích và các bản lưu có thể không còn thống nhất. Một mật khẩu vừa được cấp có thể đã bị phía khác thay thế.

Cách xử lý cần bám theo kiến trúc đã triển khai:

- Duy trì vai trò ghi hợp lệ và ngăn phía mất quyền điều phối tiếp tục ghi.
- Không tự hạ số nút cần thiết hoặc vô hiệu hóa cơ chế bảo vệ để “lấy lại availability”.
- Không coi một bản sao đọc được là đủ điều kiện cấp credential cho mọi loại truy cập.
- Khi không xác định được trạng thái credential, đánh dấu không thể cấp và đưa vào quy trình đối soát.
- Dừng tác vụ xoay vòng trên các phía không có quyền thực hiện.

Tính sẵn sàng cao cho phép chịu được một số lỗi đã dự kiến; nó không tạo ra quyền bỏ qua các điều kiện nhất quán của kho bí mật.

### 6.4. Mất audit hoặc session recording

Cần tách ít nhất ba khâu: tạo bằng chứng tại điểm thực thi, lưu bền vững và chuyển bằng chứng tới nơi tập trung.

Nếu chỉ mất kết nối chuyển tiếp, local spool có thể giúp duy trì hoạt động. Spool phải có các đặc tính được thiết kế trước: kiểm soát truy cập, bảo vệ tính toàn vẹn, mã hóa phù hợp, hạn mức dung lượng, kiểm tra lỗi và cơ chế phát lại.

Nếu không còn nơi lưu bền vững được chấp nhận, việc chỉ đẩy sự kiện vào RAM không đáp ứng cùng một bảo đảm. Tiến trình hoặc máy chủ có thể mất dữ liệu khi khởi động lại.

Bản ghi sự kiện và bản ghi nội dung phiên cũng khác nhau. Một audit event “đã mở SSH” không thay thế được video hoặc luồng lệnh nếu chính sách yêu cầu bản ghi phiên đó. Quyết định phải dựa trên đúng loại bằng chứng bắt buộc.

### 6.5. Mất kết nối tới hệ thống đích trong khi xoay credential

Một thao tác xoay credential có thể bị gián đoạn sau khi hệ thống đích đã đổi mật khẩu nhưng trước khi PAM nhận được phản hồi thành công. Timeout không chứng minh rằng phía đích chưa thay đổi.

Trong trường hợp này, không nên thử ghi liên tục hoặc tự khôi phục bí mật cũ mà chưa xác định trạng thái. Cần:

1. Đánh dấu credential đang có kết quả chưa xác định.
2. Ngăn cấp thêm credential đó theo cách giả định trạng thái đã rõ.
3. Dùng cơ chế đối soát được hỗ trợ để xác minh trạng thái tại đích.
4. Ghi lại các lần thử và kết quả mà không đưa giá trị bí mật vào log.
5. Chỉ đưa credential trở lại phục vụ khi đã xác định bản có hiệu lực và hoàn tất lưu trữ an toàn.

Đây là một lý do quan trọng để đưa quản lý trạng thái credential vào thiết kế degraded mode, thay vì chỉ theo dõi trạng thái kết nối mạng.

## 7. Thiết kế ngân sách suy giảm

Degraded mode cần giới hạn tài nguyên và thời gian. Một hệ thống có thể còn hoạt động kỹ thuật nhưng đã vượt mức rủi ro được chấp nhận.

Các giá trị dưới đây chỉ minh họa cho bài học, không phải ngưỡng khuyến nghị chung:

| Ngân sách | Giá trị minh họa | Ý nghĩa |
|---|---|---|
| Thời lượng chế độ suy giảm | 20 phút | Hết hạn thì đánh giá lại theo luồng được duyệt; không tự gia hạn |
| Phiên mới trong chế độ suy giảm | Tối đa 10 phiên cho toàn phạm vi được quản lý | Giảm tải và giới hạn lượng truy cập phát sinh |
| Grant cục bộ | Không quá 5 phút và không vượt hạn grant gốc | Hạn chế thời gian sử dụng thông tin có thể đã cũ |
| Spool audit | Dành riêng 4 GiB | Tách dung lượng khỏi nhu cầu lưu trữ thông thường |
| Ngưỡng giảm nhận phiên | 70% dung lượng spool | Có thời gian ứng phó trước khi đầy |
| Ngưỡng dừng nhận phiên mới | 85% dung lượng spool | Giữ phần còn lại cho phiên đang chạy và sự kiện kết thúc |
| Tài nguyên được phép | Danh sách cụ thể đã duyệt | Không dùng một mẫu “mọi máy chủ nội bộ” |

Nếu giới hạn phiên là toàn cụm, một bộ đếm riêng trên mỗi gateway không tự bảo đảm được giới hạn đó. Khi bộ điều phối chung mất kết nối, cần có cơ chế phân bổ hạn mức trước hoặc từ chối phần hoạt động không thể kiểm soát ngân sách. Phải ghi rõ giới hạn nào áp dụng theo node, theo vùng và theo toàn hệ thống.

Dung lượng spool cũng cần được đánh giá bằng tốc độ sinh dữ liệu, không chỉ phần trăm sử dụng. Với tốc độ tương đối ổn định, có thể ước lượng:

~~~text
thời gian còn ghi được ≈ dung lượng còn sử dụng được / tốc độ phát sinh bằng chứng
~~~

Nếu còn 600 MiB và bằng chứng phát sinh 20 MiB mỗi phút, thời gian lý thuyết là khoảng 30 phút. Trong thực tế cần trừ phần dự phòng cho burst, metadata, sự kiện đóng phiên và sai số đo. Khi bản ghi phiên tăng đột biến, ngưỡng phần trăm có thể chưa đủ để đưa ra quyết định.

Giới hạn thời gian không được phụ thuộc hoàn toàn vào đồng hồ có thể bị chỉnh lùi. Một thiết kế thường cần phân biệt thời gian tuyệt đối để đánh giá hạn token và thời gian trôi qua để giới hạn một chế độ đã bắt đầu. Nếu không còn đủ tin cậy về thời gian, phải thu hẹp hoặc dừng các quyết định phụ thuộc vào hạn hiệu lực.

## 8. Chính sách minh họa và thứ tự đánh giá

Cấu hình dưới đây mô tả ý định của một hệ thống giả định; đây không phải cú pháp cấu hình của sản phẩm PAM cụ thể.

~~~yaml
degradedMode:
  enabled: true
  cause: AUDIT_FORWARDER_UNREACHABLE
  maxDurationSeconds: 1200
  entryRequires:
    - LOCAL_AUDIT_DURABLE
    - POLICY_BUNDLE_VALID
    - TIME_CONFIDENCE_ACCEPTABLE
    - NO_SUSPECTED_GATEWAY_COMPROMISE
  newSessions:
    allowedResourceIds:
      - payment-db-maintenance
    allowedActionSets:
      - diagnostics-readonly
    requirePreissuedGrant: true
    allowGrantRenewal: false
    maxNewSessionsPerGateway: 2
  existingSessions:
    allowWithinOriginalLease: true
    allowPrivilegeExpansion: false
  credentialChanges:
    requireAuthoritativeWriter: true
    allowUncertainCredential: false
  audit:
    durableSpoolRequired: true
    mandatoryRecordingRequired: true
    stopNewSessionsAtPercent: 85
  recovery:
    requireReconciliation: true
    requireControlledExit: true
~~~

Giới hạn trong cấu hình là theo gateway, nên tổng số phiên mới của cả cụm còn phụ thuộc số gateway đang tham gia. Nếu yêu cầu thực là giới hạn toàn cụm, cần bổ sung cơ chế ngân sách tương ứng.

Một thứ tự kiểm tra cho yêu cầu mở phiên mới có thể được mô tả như sau:

~~~text
evaluateNewSession(request, health, grant, mode):
    if normalPolicyCanBeEvaluatedSafely(health):
        return evaluateNormalPolicy(request)

    if mode.isInactive or mode.isExpired:
        return DENY("DEGRADED_MODE_NOT_AVAILABLE")

    if not health.timeConfidenceAcceptable:
        return DENY("TIME_NOT_TRUSTED")

    if not health.policyBundleAuthenticAndWithinValidity:
        return DENY("POLICY_NOT_USABLE")

    if not health.requiredEvidenceCanBeStoredDurably:
        return DENY("EVIDENCE_NOT_DURABLE")

    if health.suspectedCompromise:
        return DENY("SECURITY_INCIDENT")

    if not grant.validForExactRequest(request):
        return DENY("GRANT_NOT_VALID_FOR_REQUEST")

    if not mode.permits(request.resource, request.actionSet):
        return DENY("OUTSIDE_DEGRADED_SCOPE")

    if not reserveCapacityAndRecordDecisionAtomically(request):
        return DENY("CAPACITY_OR_AUDIT_RESERVATION_FAILED")

    return ALLOW_UNTIL(earliestOf(
        grant.expiresAt,
        mode.expiresAt,
        request.originalMaximumSessionEnd
    ))
~~~

Đây là mã giả để giải thích cách ra quyết định, không phải bộ kiểm soát truy cập hoàn chỉnh. Việc kiểm tra chữ ký, chống phát lại, điều phối ngân sách, lưu quyết định và thực thi thời hạn phải do các thành phần tin cậy của hệ thống đảm nhiệm.

Đặc biệt, “kiểm tra còn chỗ” và “tăng bộ đếm” ở hai thao tác rời có thể bị nhiều yêu cầu đồng thời vượt qua. Cơ chế nhận phiên cần giữ được ngân sách trước khi phát hành quyền và xử lý được lỗi giữa các bước. Nếu phần điều phối đó không còn hoạt động, nhánh cho phép không được mặc định thành công.

## 9. Điều khiển phiên và credential trong thời gian suy giảm

### 9.1. Phiên đang chạy

Mỗi loại phiên nên có quy tắc riêng cho các sự kiện: hết lease, mất tái xác thực, mất bản ghi, mất kênh điều khiển và thay đổi mức rủi ro.

Đối với phiên đi qua proxy, đóng kết nối proxy có thể ngăn người dùng gửi thêm lệnh qua đường đó. Nhưng thao tác đã khởi chạy tại máy đích có thể tiếp tục, và một tiến trình tách khỏi phiên có thể vẫn tồn tại. Không được báo “đã chấm dứt toàn bộ quyền tại đích” chỉ từ việc đóng socket.

Nếu người dùng đã nhận credential để kết nối trực tiếp, PAM có thể không còn ở trong đường truyền để cắt phiên. Hết lease trong PAM cũng không bảo đảm hệ thống đích tự làm credential đó vô hiệu. Thiết kế phải xác định rõ khả năng thu hồi tại đích, thời hạn credential thực sự và hành động bù khi khôi phục.

### 9.2. Credential lưu cục bộ

Bộ đệm credential có thể giảm phụ thuộc vào kết nối trung tâm nhưng cũng tạo thêm điểm lưu bí mật. Cần xác định rõ:

- Credential nào được lưu, cho tài nguyên nào và trong thời gian bao lâu.
- Cách mã hóa, kiểm soát truy cập và xóa khi hết điều kiện sử dụng.
- Cơ chế ngăn cấp nhầm credential đã được xoay vòng hoặc thu hồi.
- Khả năng phát hiện credential đang ở trạng thái không xác định.
- Bằng chứng cho từng lần cấp mà không ghi giá trị bí mật vào log.

Mã hóa dữ liệu trên đĩa không tự giải quyết rủi ro dữ liệu đã cũ hoặc quyền đã bị thu hồi. Một bản cache được bảo vệ tốt vẫn có thể là nguồn sai nếu không có điều kiện hiệu lực rõ ràng.

### 9.3. Workload và tài khoản dịch vụ

Workload thường yêu cầu credential tự động và liên tục. Khi dịch vụ cấp bí mật suy giảm, việc retry đồng loạt có thể làm tăng tải và kéo dài sự cố.

Nên quy định giới hạn retry, khoảng chờ tăng dần có độ lệch, số yêu cầu đồng thời và cách trả lỗi có thể phân loại. Workload không được chuyển sang một credential dài hạn dùng chung chỉ vì không lấy được credential ngắn hạn.

Nếu workload được phép tiếp tục dùng credential đã nhận, thời gian sử dụng phải không vượt hạn thực tế và chính sách tương ứng. Đừng nhầm khả năng ứng dụng còn kết nối được với bằng chứng rằng quyền truy cập vẫn hợp lệ.

## 10. Audit trong degraded mode

Audit phải đủ để trả lời: ai được cấp quyền gì, dựa trên thông tin nào, thành phần nào ra quyết định, hệ thống đang suy giảm vì nguyên nhân nào và kết quả thực thi ra sao.

Một sự kiện minh họa:

~~~json
{
  "eventId": "evt-gw02-000184",
  "incidentId": "pam-incident-042",
  "gatewayId": "gw02",
  "eventType": "DEGRADED_SESSION_DECISION",
  "subjectId": "operator-17",
  "resourceId": "payment-db-maintenance",
  "actionSet": "diagnostics-readonly",
  "grantId": "grant-782",
  "policyVersion": "policy-118",
  "modeReason": "AUDIT_FORWARDER_UNREACHABLE",
  "decision": "ALLOW_LIMITED",
  "evidenceStorage": "LOCAL_DURABLE_SPOOL",
  "observedAt": "2026-01-15T08:10:00Z",
  "sessionNotAfter": "2026-01-15T08:14:00Z"
}
~~~

Không đưa mật khẩu, private key, bearer token, mã khôi phục hoặc toàn bộ nội dung credential vào sự kiện.

Khi chuyển tiếp trở lại, nên dùng định danh sự kiện ổn định để bên nhận xử lý bản gửi lặp mà không tạo ra các hành động lặp ngoài ý muốn. Cần giữ thông tin thứ tự tại nguồn; chỉ dựa vào timestamp có thể không đủ khi nhiều node lệch thời gian hoặc đồng bộ trở lại.

Bên gửi chỉ giải phóng dữ liệu local theo cơ chế xác nhận lưu bền vững đã thiết kế. Việc kết nối TCP thành công hoặc một API trung gian nhận request không nhất thiết chứng minh rằng bằng chứng đã được lưu ở nơi có thể phục hồi.

Nếu mất một đoạn bằng chứng, phải ghi nhận khoảng trống và đánh giá ảnh hưởng. Không tạo sự kiện giả để làm hồ sơ trông liên tục.

## 11. Quản lý vòng đời chế độ suy giảm

Một mô hình trạng thái giúp tránh việc các thành phần tự vào và ra khỏi chế độ suy giảm một cách khó kiểm soát.

~~~text
NORMAL
  → DEGRADED
  → RECOVERING
  → NORMAL

DEGRADED hoặc RECOVERING
  → RESTRICTED
  khi mất một bảo đảm bắt buộc hoặc vượt ngân sách

RESTRICTED
  → RECOVERING
  sau khi khôi phục đủ điều kiện và có quyết định hợp lệ
~~~

- **NORMAL:** các khả năng cần thiết đang đáp ứng điều kiện vận hành bình thường.
- **DEGRADED:** một tập khả năng đã bị giới hạn; lý do, phạm vi và hạn hiệu lực được công bố.
- **RESTRICTED:** từ chối các hoạt động đặc quyền không còn đáp ứng điều kiện; có thể vẫn duy trì quan sát và thao tác kiểm soát được phép.
- **RECOVERING:** phụ thuộc đã phục hồi nhưng hệ thống còn đối soát bằng chứng, quyền, phiên và credential.

Một lần kiểm tra sức khỏe thành công không đủ để chuyển ngay về NORMAL. Cần thời gian ổn định phù hợp, kiểm tra từ đúng vị trí thực thi và xác nhận các điều kiện chức năng. Ví dụ, vault trả lời health endpoint chưa chứng minh gateway đã có quyền thực hiện thao tác cần thiết với đúng tài nguyên.

Để hạn chế chuyển trạng thái liên tục khi mạng chập chờn, thiết kế có thể sử dụng cửa sổ quan sát và ngưỡng vào/ra khác nhau. Tuy nhiên, cơ chế chống dao động không được kéo dài việc cho phép truy cập khi một bảo đảm bắt buộc đã mất.

## 12. Runbook vận hành

### Bước 1: Xác nhận tác động

Ghi nhận sự cố, phạm vi ảnh hưởng và nguồn phát hiện. Xác định lỗi thuộc mặt phẳng danh tính, chính sách, credential, phiên hay bằng chứng. Kiểm tra từ gateway và các thành phần thực thi, không chỉ từ màn hình tổng quan.

Đồng thời phân biệt sự cố khả dụng với dấu hiệu xâm nhập. Nếu nghi ngờ gateway, vault hoặc nguồn chính sách bị chiếm quyền, chế độ duy trì hoạt động dựa trên độ tin cậy của chính thành phần đó có thể không còn phù hợp.

### Bước 2: Chọn chính sách suy giảm đã duyệt

Đối chiếu nguyên nhân và các điều kiện còn giữ được. Xác định rõ hoạt động nào tiếp tục, hoạt động nào bị từ chối, tài nguyên nào nằm trong phạm vi và thời điểm bắt buộc kết thúc.

Nếu không có chính sách phù hợp, không tự dựng một ngoại lệ rộng trong lúc xử lý sự cố. Chuyển yêu cầu khẩn cấp sang quy trình được ủy quyền tương ứng.

### Bước 3: Kích hoạt và thông báo

Gắn trạng thái với incident ID, người chịu trách nhiệm và thời hạn. Thông báo rõ cho đội vận hành: hành động nào còn sử dụng được, lỗi nào là chủ đích và đường xử lý yêu cầu khẩn cấp ở đâu.

Một thông báo “PAM đã khôi phục một phần” không đủ nếu người vận hành không biết phiên mới đang bị giới hạn vào tài nguyên nào.

### Bước 4: Theo dõi ngân sách và điều kiện dừng

Theo dõi thời gian còn lại, dung lượng bằng chứng, số phiên đang hoạt động, credential chưa xác định trạng thái và yêu cầu bị từ chối.

Khi chạm điều kiện dừng, hệ thống cần thực thi quy tắc đã định; không chỉ gửi thêm cảnh báo rồi tiếp tục cấp quyền. Nếu cần một ngoại lệ mới, phải có quyết định mới qua luồng được ủy quyền.

### Bước 5: Phục hồi và đối soát

Xác nhận phụ thuộc thực sự phục hồi; chuyển sang RECOVERING. Phát lại bằng chứng, đối soát quyết định cục bộ và kiểm tra trạng thái credential. Chỉ mở lại chức năng theo điều kiện của từng khả năng.

### Bước 6: Đóng chế độ suy giảm

Xác minh không còn ngoại lệ hết hạn đang dùng, không còn yêu cầu cấp quyền treo và các phiên cần thu hồi đã được xử lý. Lưu bằng chứng chuyển trạng thái, đánh giá khoảng trống và cập nhật runbook sau sự cố.

## 13. Tình huống thực hành: mất đường chuyển tiếp audit

Giả sử một cụm PAM phục vụ đội vận hành cơ sở dữ liệu. Chính sách yêu cầu audit sự kiện và bản ghi phiên; gateway có nơi lưu cục bộ được chấp nhận cho cả hai loại bằng chứng.

Tại phút 0, đường truyền tới kho trung tâm mất kết nối. Gateway vẫn xác minh được danh tính, đánh giá grant và ghi bền vững. Hệ thống chuyển sang DEGRADED với phạm vi chỉ đọc chẩn đoán trên một nhóm tài nguyên cụ thể.

Tại phút 4, một kỹ sư yêu cầu mở phiên chẩn đoán bằng grant còn hiệu lực. Gateway xác minh đúng chủ thể, tài nguyên, tập hành động và hạn sử dụng; giữ chỗ trong ngân sách; ghi quyết định rồi mới tạo phiên.

Tại phút 7, một kỹ sư khác yêu cầu phiên để thay đổi cấu hình. Dù người này có vai trò quản trị trong điều kiện bình thường, yêu cầu bị từ chối vì chế độ suy giảm chỉ cho phép tập hành động chẩn đoán.

Tại phút 11, tốc độ sinh bản ghi tăng nhanh. Dung lượng hiện tại chưa vượt ngưỡng dừng nhưng dự báo thời gian còn ghi được đã thấp hơn phần dự phòng cho các phiên đang chạy. Gateway dừng nhận phiên mới và áp dụng chính sách cho phiên hiện hữu.

Tại phút 14, kết nối trở lại. Hệ thống chuyển sang RECOVERING, phát lại dữ liệu theo định danh sự kiện và xác nhận lưu trữ. Việc chuyển tiếp được ưu tiên và giới hạn tốc độ phù hợp để không làm các dịch vụ vừa phục hồi quá tải.

Tại phút 18, hệ thống xác nhận bằng chứng đã đối soát, ngân sách đã trở lại mức cho phép, không có credential không rõ trạng thái và các phép thử chức năng đạt yêu cầu. Người chịu trách nhiệm cho phép kết thúc chế độ suy giảm.

Trong ví dụ này, khả năng tiếp tục phiên không đến từ việc bỏ yêu cầu audit. Nó đến từ một đường lưu bằng chứng dự phòng đã được chấp nhận và còn đủ năng lực.

## 14. Phục hồi không chỉ là đưa health check về màu xanh

Sau một khoảng thời gian suy giảm, hệ thống trung tâm có thể chưa biết đầy đủ những gì đã xảy ra tại gateway. Quá trình phục hồi cần giải quyết các nhóm dữ liệu sau.

### Bằng chứng

Đối chiếu số lượng sự kiện, các khoảng thứ tự tại nguồn, bản ghi phiên và xác nhận nhận dữ liệu. Phân loại sự kiện gửi lặp, dữ liệu còn tồn và khoảng trống không thể phục hồi.

### Quyền và phiên

Kiểm tra grant nào đã được dùng, quyền nào bị thu hồi trong thời gian mất kết nối và phiên nào vẫn tồn tại. Áp dụng quyết định thu hồi theo khả năng thực thi tại đích; ghi nhận trường hợp chưa xác minh được.

### Credential

Đối soát từng thao tác xoay vòng có kết quả chưa rõ. Với credential khẩn cấp đã được sử dụng, thực hiện quy trình thay đổi, vô hiệu hóa hoặc thu hồi phù hợp sau sự cố và xác nhận tại hệ thống đích.

Không giả định rằng khôi phục một bản sao vault cũ sẽ đồng bộ trạng thái credential với các máy chủ đã đổi mật khẩu trong thời gian sự cố. Khôi phục dữ liệu và xác định credential thực sự có hiệu lực là hai công việc liên quan nhưng khác nhau.

### Hàng đợi công việc

Không phát lại mù mọi yêu cầu quản trị đang chờ. Yêu cầu có thể đã hết hạn, bị hủy hoặc đã thực hiện tại đích dù phía PAM chưa nhận được kết quả. Cần xác minh tính hợp lệ hiện tại và xử lý khả năng lặp trước khi thực hiện lại.

### Tải sau phục hồi

Một đợt reconnect, lấy credential và chuyển log đồng thời có thể làm dịch vụ vừa phục hồi lại quá tải. Nên mở lại chức năng theo từng nhóm, giới hạn tốc độ và theo dõi độ trễ, lỗi cùng độ sâu hàng đợi.

## 15. Kiểm thử thiết kế degraded mode

Kiểm thử cần diễn ra trong môi trường và phạm vi được cho phép, với phương án khôi phục rõ ràng. Mỗi tình huống phải có kết quả mong đợi đo được.

| Tình huống thử | Bằng chứng cần quan sát |
|---|---|
| Ngắt kết nối tới IdP | Yêu cầu xác thực mới không tự bỏ MFA; phiên hiện hữu tuân thủ hạn và yêu cầu tái xác thực |
| Mất dịch vụ phê duyệt | Không có phê duyệt mới giả định; grant cũ chỉ dùng đúng phạm vi và thời hạn |
| Phân vùng mạng giữa các node | Phía không có quyền ghi không cấp hoặc xoay credential trái cơ chế điều phối |
| Mất kho audit trung tâm | Bằng chứng vẫn ghi bền vững cục bộ và có hạn mức |
| Làm local spool gần đầy | Hệ thống giảm hoặc dừng nhận phiên đúng ngưỡng; còn phần dự phòng đã thiết kế |
| Khởi động lại gateway khi có dữ liệu chưa gửi | Bằng chứng và trạng thái cần thiết phục hồi theo thiết kế; không tự xóa giới hạn thời gian |
| Thay đổi hoặc mất tin cậy về thời gian | Không kéo dài grant, lease hay chế độ suy giảm ngoài giới hạn |
| Timeout trong lúc xoay credential | Credential được đưa vào trạng thái cần đối soát, không được cấp dựa trên phỏng đoán |
| Gửi lại một yêu cầu hoặc một grant | Cơ chế chống lặp và giới hạn số lần dùng vẫn có hiệu lực theo thiết kế |
| Phục hồi kết nối chập chờn | Không mở lại toàn bộ chức năng chỉ sau một lần thành công |
| Cấp quyền đồng thời tại nhiều gateway | Hạn mức được thực thi đúng phạm vi node hoặc toàn cụm đã cam kết |
| Kết thúc phiên proxy | Xác minh được điều gì đã bị ngắt và điều gì còn có thể tồn tại trên máy đích |

Một bài kiểm thử chỉ chứng minh “người dùng vẫn đăng nhập được” là chưa đủ. Cần kiểm tra cả nhánh cho phép, nhánh từ chối, hành vi khi hết hạn và dữ liệu phục hồi.

## 16. Lỗi thiết kế thường gặp

**Dùng tài khoản quản trị dùng chung khi PAM lỗi.** Cách này làm yếu khả năng quy trách nhiệm và có thể tạo ra một credential tồn tại lâu hơn sự cố. Nếu cần truy cập khẩn cấp, phải đi qua luồng được thiết kế cho mục đích đó.

**Coi cache là nguồn quyền vô thời hạn.** Thông tin từng đúng không đồng nghĩa luôn đúng. Cache phải gắn với điều kiện hiệu lực, phạm vi, nguồn gốc và cách xử lý khi không thể kiểm tra thu hồi.

**Tự động gia hạn chế độ suy giảm mỗi lần tiến trình khởi động lại.** Điều này có thể biến một ngoại lệ ngắn thành trạng thái thường trực. Mốc bắt đầu và hạn kết thúc cần được duy trì, xác minh theo thiết kế.

**Chỉ theo dõi CPU và health endpoint.** PAM cần đo cả khả năng đánh giá quyền, cấp và thu hồi credential, điều khiển phiên và lưu bằng chứng.

**Dừng nhận phiên khi đĩa đã đầy.** Khi đó hệ thống có thể không còn chỗ ghi sự kiện kết thúc hoặc bản ghi của phiên đang chạy. Cần hạn mức và phần dự phòng trước khi đạt mức đầy.

**Tự thử lại thao tác đặc quyền sau timeout.** Thao tác có thể đã hoàn tất tại đích. Việc thực hiện lại có thể gây thay đổi lặp hoặc làm credential lệch trạng thái.

**Về NORMAL trước khi đối soát.** Cách này che giấu grant đã dùng, credential chưa rõ trạng thái hoặc bằng chứng còn tồn; có thể mở rộng tải khi hệ thống chưa sẵn sàng.

## 17. Tự kiểm tra kiến thức

1. Kho tìm kiếm audit không truy cập được nhưng gateway vẫn lưu đủ bằng chứng bền vững. Vì sao tình huống này khác với việc gateway không thể ghi audit?
2. Một phiên còn 3 phút lease khi dịch vụ chính sách mất kết nối. Vì sao “được tiếp tục tới hạn gốc” không có nghĩa là “được gia hạn thêm 3 phút”?
3. Một grant chỉ dùng một lần được đưa tới hai gateway đang phân vùng mạng. Thiết kế phải giải quyết rủi ro nào trước khi cho phép dùng grant?
4. Vì sao đóng kết nối proxy chưa đủ để khẳng định mọi tác vụ đặc quyền ở hệ thống đích đã dừng?
5. Khi xoay credential bị timeout sau lệnh thay đổi tại đích, vì sao không thể kết luận rằng bí mật cũ vẫn còn đúng?
6. Những đối soát nào phải hoàn tất trước khi ra khỏi RECOVERING?

Gợi ý trả lời: tập trung vào bảo đảm còn giữ được, phạm vi quyền đã cấp, khả năng điều phối và bằng chứng thực thi. Degraded mode có chất lượng khi nó xác định rõ những gì hệ thống vẫn chứng minh được, thực thi các giới hạn tương ứng và đưa mọi trạng thái phát sinh trở lại quy trình quản lý sau khi phục hồi.
