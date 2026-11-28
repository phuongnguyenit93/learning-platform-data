# Failure domain của IAM

## 1. Failure domain là gì trong hệ thống danh tính?

**Failure domain**, hay miền sự cố, là một phạm vi gồm các thành phần có thể cùng bị ảnh hưởng bởi một nguyên nhân chung. Trong IAM, nguyên nhân đó có thể là một vùng hạ tầng, database, hệ thống DNS, khóa ký, cấu hình trust, bản policy, nguồn thuộc tính hoặc quyền quản trị dùng chung.

Ví dụ, ba ứng dụng dùng cùng một IdP. IdP có nhiều instance nhưng tất cả cùng phụ thuộc một database. Khi database không đáp ứng, thêm instance IdP không giúp đăng nhập hoạt động trở lại. Database là một phụ thuộc tạo ra miền sự cố chung cho các instance và những hành trình đăng nhập dựa vào chúng.

Miền sự cố không chỉ liên quan đến máy chủ bị tắt. Một bản policy sai được phát hành đồng thời có thể từ chối tất cả người dùng hợp lệ; một khóa ký bị lộ có thể làm mất độ tin cậy của credential; một lỗi mapping có thể gắn người dùng với tài khoản sai. Các thành phần vẫn trả HTTP 200 nhưng mục tiêu bảo mật đã không còn được bảo đảm.

Phân tích failure domain giúp trả lời: **khi một nguyên nhân xảy ra, chức năng IAM nào bị ảnh hưởng, những ứng dụng và chủ thể nào nằm trong phạm vi đó, và giới hạn nào ngăn sự cố lan rộng?**

## 2. Phân biệt miền sự cố, điểm lỗi và phạm vi ảnh hưởng

| Khái niệm | Ý nghĩa | Ví dụ trong IAM |
| --- | --- | --- |
| Điểm lỗi đơn, single point of failure | Một thành phần đơn lẻ có thể làm gián đoạn chức năng cần thiết | Kho session duy nhất không có đường phục hồi phù hợp |
| Miền sự cố | Nhóm cùng chịu tác động từ một nguyên nhân | Các instance IdP cùng dùng một database hoặc một cấu hình phát hành |
| Phạm vi ảnh hưởng, blast radius | Các đối tượng và chức năng thật sự bị tác động trong một tình huống | Chỉ đăng nhập mới của tenant A, hay mọi API của mọi tenant |
| Dự phòng, redundancy | Có nhiều thành phần thay thế để tiếp tục phục vụ | Nhiều instance PDP hoặc replica dữ liệu |
| Cô lập, isolation | Giới hạn đường lan truyền lỗi hoặc thẩm quyền | Tách cell phục vụ, tài nguyên, quota và phạm vi quản trị |

Nhiều bản sao không tự tạo nhiều miền độc lập. Nếu tất cả chạy cùng phiên bản lỗi, dùng chung khóa bị thu hồi hoặc nhận cùng một cấu hình sai, chúng vẫn có thể hỏng đồng thời.

Ngược lại, một miền bị lỗi không nhất thiết làm mọi chức năng ngừng hoạt động. IdP không cấp được token mới có thể ảnh hưởng đăng nhập và refresh, trong khi một API vẫn xác minh được token còn hiệu lực bằng cấu hình tin cậy cục bộ. Khả năng tiếp tục này còn phụ thuộc trạng thái thu hồi, policy và các kiểm tra runtime mà API thực sự yêu cầu.

## 3. Những dạng sự cố cần đưa vào mô hình

### 3.1. Mất sẵn sàng hoặc tăng độ trễ

IdP timeout, PDP quá tải, directory không truy vấn được hoặc dịch vụ MFA bên ngoài không phản hồi có thể khiến giao dịch không hoàn tất. Tăng độ trễ còn có thể giữ kết nối và worker lâu, làm các thành phần gọi nó cạn tài nguyên rồi kéo theo sự cố thứ cấp.

### 3.2. Quyết định sai về truy cập

Một lỗi có thể gây **từ chối sai**, cản người đáng lẽ được phép, hoặc **cho phép sai**, cấp quyền ngoài chính sách. Hai trường hợp có thể cần cách xử lý khác nhau. Một đợt giảm deny đột ngột sau deploy không tự là cải thiện; hệ thống có thể đã bỏ qua kiểm tra hoặc cấp role quá rộng.

### 3.3. Mất tính toàn vẹn của danh tính và cấu hình trust

Khóa ký bị lộ, issuer không được phép được thêm vào trust hoặc mapping tài khoản sai có thể làm hệ thống chấp nhận bằng chứng không đúng chủ thể. Failover sang một instance khác sử dụng cùng vật liệu hoặc cùng cấu hình chưa sửa sẽ không giải quyết nguyên nhân.

### 3.4. Trạng thái cũ và thu hồi không có hiệu lực

Hệ thống trung tâm đã thu hồi quyền nhưng cache, session, token hoặc replica vẫn giữ trạng thái cũ. Các endpoint có thể vẫn phản hồi nhanh và không báo lỗi, trong khi mục tiêu chấm dứt truy cập chưa đạt.

### 3.5. Lộ dữ liệu danh tính

Log, bản sao hồ sơ hoặc kho thuộc tính tập trung bị truy cập ngoài phạm vi có thể ảnh hưởng nhiều ứng dụng và người dùng. Đây là miền ảnh hưởng về dữ liệu; bổ sung máy chủ dự phòng không làm giảm số dữ liệu được chia sẻ hoặc quyền của một tài khoản quản trị quá rộng.

### 3.6. Mất khả năng quản trị và phục hồi

Nếu console hạ tầng, kho secret và công cụ giám sát đều cần đăng nhập qua chính IdP đang lỗi, đội vận hành có thể không truy cập được công cụ phục hồi. Cần xem cả đường truy cập của người xử lý sự cố, không chỉ đường người dùng cuối.

## 4. Lập bản đồ phụ thuộc theo từng hành trình

Không nên bắt đầu bằng câu “IAM có ba node nên đã chịu lỗi”. Hãy bắt đầu bằng một hành trình cụ thể, liệt kê các phụ thuộc đồng bộ và trạng thái cần thiết để hành trình đó thành công.

```text
Đăng nhập mới
  → DNS và mạng
  → endpoint IdP
  → dữ liệu tài khoản/credential
  → yếu tố xác thực bổ sung nếu được yêu cầu
  → khóa và trạng thái cần cho phát hành kết quả
  → callback, mapping và session tại ứng dụng
```

Một luồng API khác có thể là:

```text
Request có access token
  → xác minh credential tại API hoặc thành phần được tin cậy
  → kiểm tra trạng thái/thu hồi nếu thiết kế yêu cầu
  → PDP hoặc policy và thuộc tính cục bộ
  → kiểm tra tài nguyên và tenant
  → thực thi quyền
```

Hai hành trình có thể chia sẻ một số thành phần nhưng không phải tất cả. Đây là lý do phải xác định failure domain theo chức năng, thay vì gắn một nhãn “IAM down” cho mọi trường hợp.

| Hành trình | Phụ thuộc thường cần xem xét | Câu hỏi về phạm vi ảnh hưởng |
| --- | --- | --- |
| Đăng nhập mới | IdP, nguồn credential, MFA, trust và session | Ai không thể tạo phiên mới? |
| Refresh token | Token service, grant store, client authentication | Client/thiết bị nào không thể duy trì truy cập? |
| Xác minh token cục bộ | Khóa tin cậy, thời gian, cấu hình, trạng thái bổ sung nếu có | Token nào còn được chấp nhận theo đúng hợp đồng? |
| Introspection hoặc trạng thái trực tuyến | Endpoint xác minh, dữ liệu token/quyền | API nào phụ thuộc kết quả mới trên mỗi request? |
| Quyết định quyền | PDP, policy, thuộc tính, dữ liệu tài nguyên | Hành động nào phải dừng khi thiếu quyết định tin cậy? |
| Thu hồi/vô hiệu hóa | Quản trị, event, connector, session/cache downstream | Mất bao lâu để điểm thực thi từ chối truy cập? |
| Khôi phục sự cố | Credential quản trị, console, mạng, backup và khóa | Người có trách nhiệm có thể vào công cụ phục hồi không? |

Đưa cả phụ thuộc gián tiếp vào bản đồ: DNS dùng chung, nguồn thời gian, CA, dịch vụ quản lý khóa, secret store, pipeline phát hành và hệ thống cấu hình. Một nền tảng nhìn có nhiều vùng có thể vẫn phụ thuộc vào một đường quản trị hoặc một kho trust chung.

## 5. Các miền sự cố thường gặp

### 5.1. Tiến trình, node và tài nguyên cục bộ

Một instance có thể hỏng, cạn memory hoặc hết connection pool. Nhiều instance và cơ chế điều phối phù hợp có thể giới hạn tác động, nhưng cần bảo đảm tải chuyển sang các instance còn lại không làm chúng quá tải tiếp.

### 5.2. Zone, region và mạng

Mất một khu vực hạ tầng có thể ảnh hưởng compute, storage, route và đường truy cập tới phụ thuộc. Phân bố nhiều vùng giúp giảm một số nguyên nhân chung, nhưng chỉ khi các phụ thuộc và đường failover cũng được thiết kế tương ứng.

Nếu cả hai vùng vẫn gọi một database hoặc một dịch vụ khóa chỉ có ở vùng đã mất, việc có instance tại vùng còn lại chưa đủ để phục vụ. Khả năng đọc dữ liệu cũng chưa đồng nghĩa có thể ghi session, grant hoặc trạng thái thu hồi một cách đúng đắn.

### 5.3. Dữ liệu danh tính, session và grant

Một database dùng chung có thể là miền sự cố lớn. Replica giúp một số tình huống, nhưng độ trễ sao chép và tính nhất quán có ý nghĩa bảo mật: replica cũ có thể chưa biết một tài khoản đã bị khóa hoặc refresh token đã bị thu hồi.

Chuyển quyền ghi cần xử lý xung đột và tránh nhiều bên cùng phát hành trạng thái trái nhau. Không ưu tiên “ghi được ở mọi nơi” mà bỏ qua ràng buộc chống tái sử dụng hoặc tính đúng của vòng đời credential.

### 5.4. Khóa, chứng thư và trust

Nhiều instance cùng dùng một khóa ký có cùng miền ảnh hưởng khi khóa đó bị lộ hoặc cần thu hồi. Ngược lại, chia khóa theo phạm vi có thể giảm ảnh hưởng nhưng làm tăng yêu cầu quản lý trust, luân chuyển và phục hồi.

Một root trust hoặc quyền quản trị chung vẫn có thể nối lại những miền tưởng như đã tách. Phải xét ai có thể sửa cấu hình bên nhận, thêm khóa hoặc thay issuer, không chỉ xét file khóa được đặt ở đâu.

### 5.5. Policy, cấu hình và bản phát hành

Một bản policy hoặc phần mềm lỗi có thể được phát hành đồng thời trên mọi replica. Đây là lỗi tương quan theo thay đổi. Tách vùng vật lý không ngăn được nếu tất cả nhận bản lỗi cùng lúc.

Phát hành từng phần, giới hạn phạm vi và kiểm tra quyền hiệu lực có thể giúp phát hiện sớm trước khi lan rộng. Rollback cũng cần xem các thay đổi thu hồi hoặc bảo mật đã xảy ra; không khôi phục một policy cũ vô tình mở lại quyền đã được gỡ hợp lệ.

### 5.6. Tenant, workload và bên cung cấp ngoài

Một tenant tạo lưu lượng lớn có thể làm cạn tài nguyên dùng chung của IdP hoặc PDP, ảnh hưởng tenant khác. Quota và pool tài nguyên cần phù hợp với từng nhóm tải, gồm cả request quản trị, refresh, callback và provisioning.

MFA, email khôi phục, IdP đối tác hoặc directory bên ngoài cũng tạo miền phụ thuộc. Sự cố một kết nối đối tác không nên làm mọi kết nối còn lại cạn worker do timeout hoặc retry không giới hạn.

## 6. Dự phòng không đồng nghĩa độc lập

Giả sử ba instance IdP cùng hoạt động sau load balancer. Một mô hình chỉ xét xác suất từng instance hỏng độc lập sẽ đánh giá quá lạc quan nếu bỏ qua database, mạng, cấu hình và khóa dùng chung.

Trong một mô hình minh họa đơn giản, nếu `q` là xác suất phụ thuộc chung không đáp ứng, còn `p` là xác suất mỗi instance hỏng độc lập khi phụ thuộc chung hoạt động, thì:

```text
P(không phục vụ được) = q + (1 - q) × p³
```

Công thức chỉ minh họa một cấu trúc phụ thuộc với những giả định cụ thể, không phải cách tính SLO hoàn chỉnh cho IAM thực tế. Nó cho thấy tăng số instance không loại bỏ phần lỗi do `q`. Trong thực tế còn phải xét lỗi phần mềm tương quan, failover không thành công, giới hạn tải và các phụ thuộc khác.

Tương tự, không nhân các số availability của nhiều dịch vụ rồi coi kết quả là độ sẵn sàng đầu cuối nếu chưa biết quan hệ phụ thuộc và giả định độc lập. Đo hành trình thực tế và phân tích nguyên nhân chung thường cho thông tin hành động tốt hơn một phép tính từ các SLA riêng lẻ.

## 7. Cô lập để giới hạn sự cố lan truyền

### 7.1. Tách đường quản trị và đường phục vụ runtime

Tạo tài khoản, phê duyệt role, phát hành policy và thay trust là các thao tác quản trị. Đăng nhập, cấp token, xác minh credential và quyết định quyền là các đường runtime. Chúng có thể chia sẻ dữ liệu, nhưng nên xác định rõ phụ thuộc và tài nguyên của từng đường.

Một đợt import tài khoản lớn không nên làm cạn pool phục vụ đăng nhập. Một lỗi giao diện quản trị không nhất thiết phải dừng API xác minh token. Tuy nhiên, việc tách tên dịch vụ không đủ nếu chúng vẫn tranh chấp cùng tài nguyên không giới hạn.

### 7.2. Bulkhead, giới hạn tải và timeout

Bulkhead là việc chia tài nguyên thành các nhóm có giới hạn để lỗi ở một nhóm không chiếm hết tài nguyên của nhóm khác. Có thể tách connection pool, worker, quota hoặc hàng đợi theo loại hành trình hay kết nối IdP phù hợp.

Timeout cần nằm trong ngân sách của hành trình; retry cần có giới hạn và độ giãn phù hợp. Nếu nhiều tầng cùng retry, số lần gọi một phụ thuộc có thể tăng mạnh đúng lúc nó đang suy giảm. Không retry các thao tác có tác động hoặc credential sử dụng một lần một cách mù quáng.

Circuit breaker có thể hạn chế tiếp tục gây tải lên phụ thuộc đang lỗi, nhưng không tạo ra bằng chứng xác thực hoặc quyết định quyền. Mở circuit không đồng nghĩa được phép bỏ qua kiểm soát truy cập.

### 7.3. Cell và phạm vi cấu hình

Một cell có thể phục vụ một nhóm tenant hoặc ứng dụng với tài nguyên runtime và trạng thái được phân vùng. Thiết kế này có thể giới hạn sự cố nếu đường quản trị, cấu hình, khóa và phụ thuộc cũng được phân tích rõ.

Tách schema hoặc gắn `tenant_id` không tự cô lập một migration lỗi chạy trên database chung. Dùng khóa khác nhau cũng chưa đủ nếu cùng một tài khoản quản trị có thể sửa trust cho mọi cell. Cần chỉ rõ miền nào đã được tách và nguyên nhân chung nào vẫn còn.

### 7.4. Triển khai thay đổi theo phạm vi nhỏ

Canary hoặc rollout theo nhóm có thể giới hạn ảnh hưởng của phần mềm, policy và cấu hình mới. Với IAM, kiểm tra không chỉ tỷ lệ thành công mà còn những truy cập phải bị từ chối, ranh giới tenant và trạng thái thu hồi.

Một bản mới làm mọi request đều được allow có thể có ít lỗi HTTP hơn nhưng là một thất bại bảo mật nghiêm trọng. Điều kiện dừng rollout phải bao gồm tính đúng của quyền và trust, không chỉ độ trễ hoặc số lần đăng nhập thành công.

## 8. Thiết kế chế độ suy giảm có giới hạn

### 8.1. Phân biệt lỗi với deny của chính sách

PDP timeout không có nghĩa policy vừa đưa ra quyết định `deny`. Ứng dụng có thể chặn thao tác theo fail closed, nhưng dữ liệu vận hành cần ghi rõ lỗi đánh giá và kết quả thực thi bị chặn. Nếu gộp tất cả thành deny thông thường, đội vận hành có thể không nhận ra miền phụ thuộc đang hỏng.

Tương tự, lỗi IdP không nên làm tăng bộ đếm “sai mật khẩu” hoặc khóa hàng loạt tài khoản hợp lệ. Xử lý lỗi phụ thuộc khác với xử lý credential sai là điều cần thiết để sự cố không lan sang vòng đời tài khoản.

### 8.2. Dùng dữ liệu cục bộ chỉ khi còn đáp ứng hợp đồng

Một API có thể xác minh token bằng khóa đã được tin cậy trong cache nếu đáp ứng các điều kiện của thiết kế. Một engine cục bộ có thể sử dụng policy đã xác minh trong khoảng thời gian cho phép. Cần nêu rõ:

- Nguồn và tính toàn vẹn của dữ liệu được dùng.
- Phiên bản, thời hạn và độ mới tối đa chấp nhận được.
- Loại hành động được phép sử dụng chế độ này.
- Cơ chế thu hồi hoặc giới hạn khi không nhận được cập nhật.
- Điều kiện buộc dừng thay vì tiếp tục dùng bản cũ.

“Bản đã xác minh gần nhất” không bảo đảm vẫn phản ánh mọi thay đổi vừa xảy ra. Nếu một quyền đã bị thu hồi ở trung tâm nhưng chưa tới cache, dùng cache vẫn có rủi ro truy cập bằng quyền cũ. Chính sách suy giảm phải chấp nhận có chủ đích hoặc loại bỏ cửa sổ này theo yêu cầu của từng thao tác.

### 8.3. Không mở rộng trust khi gặp sự cố

Không bỏ qua chữ ký, audience, issuer, MFA bắt buộc hoặc trạng thái tài khoản để làm giảm lỗi. Không tự chuyển sang IdP chưa được phê duyệt hoặc chấp nhận mọi khóa khi gặp một key ID chưa biết.

Các hành động đặc quyền có thể cần dữ liệu mới và phải tạm dừng khi thiếu nguồn tin cậy. Một số thao tác khác có thể tiếp tục trong giới hạn đã thiết kế. Không suy rộng rằng một API còn hoạt động nghĩa là toàn bộ hệ thống đang ở trạng thái an toàn như bình thường.

## 9. Thu hồi quyền là một hành trình chịu lỗi riêng

Một yêu cầu vô hiệu hóa có thể đi qua governance, IAM, event bus, connector, session store, cache và ứng dụng. Mỗi thành phần là một nơi có thể làm cập nhật bị trì hoãn hoặc mất dấu.

```text
Yêu cầu thu hồi
  → ghi trạng thái có thẩm quyền
  → phân phối thay đổi
  → áp dụng tại từng hệ thống đích
  → điểm thực thi từ chối quyền cũ
  → xác minh và ghi nhận kết quả
```

Nếu event bus ngừng hoạt động, đăng nhập mới có thể vẫn bình thường trong khi việc thu hồi chậm lại. Chỉ theo dõi availability của endpoint đăng nhập sẽ bỏ qua sự cố này.

Đo backlog, tuổi của thay đổi chưa áp dụng, trạng thái từng đích và thời gian đến khi quyền cũ thật sự bị từ chối. Retry phải chống trùng, không phục hồi quyền bằng sự kiện cũ và không đánh dấu hoàn tất chỉ vì sự kiện đã được gửi.

Token tự chứa và session cục bộ tạo thêm cửa sổ hiệu lực. Kế hoạch cần biết điểm nào kiểm tra trạng thái mới, điểm nào chỉ dựa trên thời hạn credential và hành động nào không được tiếp tục bằng dữ liệu cũ.

## 10. Phục hồi: đúng trạng thái trước khi mở lại truy cập

### 10.1. RTO và RPO có ý nghĩa bảo mật

**Recovery Time Objective — RTO** là mục tiêu thời gian phục hồi chức năng. **Recovery Point Objective — RPO** biểu diễn mục tiêu về mức mất dữ liệu theo thời gian. Trong IAM, dữ liệu có thể bao gồm khóa tài khoản, thay đổi MFA, grant, refresh token, trust và quyền đã thu hồi.

Một bản phục hồi nhanh nhưng thiếu các lệnh thu hồi mới có thể mở lại truy cập không được phép. Vì vậy, cần nêu rõ trạng thái bảo mật nào phải được đối soát trước khi đưa dịch vụ trở lại.

### 10.2. Khôi phục trong môi trường kiểm soát

Một trình tự minh họa:

```text
Phục hồi dữ liệu và cấu hình trong môi trường cách ly
  → xác minh nguồn và phiên bản trust/khóa
  → áp dụng trạng thái vòng đời và thu hồi đủ mới
  → kiểm tra quyền, session và credential theo kế hoạch
  → mở lại từng phạm vi có kiểm soát
  → theo dõi và đối soát các thay đổi còn chờ
```

Không dùng duy nhất ledger nằm trong chính snapshot cũ để xác định mọi thay đổi xảy ra sau snapshot đó. Cần cơ chế phục hồi hoặc đối soát từ nguồn đủ mới được bảo vệ. Phải xử lý cả event đến muộn và các connector có thể tái tạo tài khoản.

### 10.3. Sự cố khóa khác với lỗi endpoint

Nếu một endpoint IdP bị lỗi nhưng khóa và trust còn an toàn, cách phục hồi khác với tình huống khóa ký bị lộ. Trong tình huống lộ khóa, đưa endpoint về trạng thái hoạt động không tự khôi phục độ tin cậy của credential đã phát hành hoặc có thể bị giả mạo.

Cần quy trình giới hạn phạm vi, thay thế/thu hồi vật liệu và cập nhật các bên xác minh theo thiết kế. Không tiếp tục tin khóa bị lộ chỉ để tránh gián đoạn, cũng không thay một khóa dùng chung mà không xác định các ứng dụng và workload sẽ bị ảnh hưởng.

## 11. Đường quản trị khẩn cấp cũng có miền sự cố

Cần kiểm tra chuỗi phụ thuộc để người vận hành truy cập console, kho secret, backup và công cụ giám sát. Một credential khẩn cấp được lưu trong vault nhưng vault chỉ mở được qua IdP đang lỗi không tạo ra đường phục hồi độc lập cho tình huống đó.

Cơ chế break-glass, nếu được thiết kế, phải có phạm vi, người chịu trách nhiệm, xác thực và kiểm soát sử dụng phù hợp. Việc sử dụng cần được ghi nhận, giới hạn thời gian và rà soát sau sự cố. Không tạo một tài khoản quản trị toàn quyền dùng chung và bỏ qua audit để đạt mục tiêu dự phòng.

Tính độc lập nên gắn với những tình huống cụ thể. Tách đường đăng nhập nhưng vẫn dùng cùng mạng hoặc cùng khóa có thể chỉ giải quyết một phần nguyên nhân. Phải diễn tập đường phục hồi trong đúng điều kiện phụ thuộc bị mất mà thiết kế dự kiến chịu được.

## 12. Quan sát phạm vi ảnh hưởng

### 12.1. Đo hành trình và phân tách kết quả

Những tín hiệu cần nhìn cùng nhau gồm:

| Tín hiệu | Vấn đề có thể nhận diện |
| --- | --- |
| Tỷ lệ đăng nhập hoàn tất theo ứng dụng/kết nối | Lỗi IdP, federation hoặc callback theo phạm vi |
| Lỗi và độ trễ cấp/refresh token | Vấn đề token service, grant store hoặc phụ thuộc |
| Lỗi xác minh và khóa chưa biết | Trust, luân chuyển khóa hoặc cấu hình tại bên nhận |
| Lỗi đánh giá quyền và kết quả thực thi | PDP/thuộc tính không sẵn sàng, fail closed |
| Phiên bản và tuổi policy/cache | Instance dùng trạng thái cũ hoặc phân phối bị đình trệ |
| Độ trễ thu hồi và tuổi backlog | Vòng đời quyền chưa đến điểm thực thi |
| Mất telemetry và hàng đợi audit | Mất khả năng quan sát hoặc bằng chứng |

Một tỷ lệ lỗi 0% khi không còn giao dịch được ghi nhận không chứng minh hệ thống khỏe. Cần quan sát mẫu số, lưu lượng, coverage và tình trạng pipeline. Tương tự, một instance trả health check đơn giản không chứng minh hành trình cần database/MFA đang hoạt động.

### 12.2. Phân tách theo ranh giới có ý nghĩa

Tổng hợp theo dịch vụ, vùng, cell, loại hành trình, kết nối hoặc phiên bản được kiểm soát giúp khoanh vùng. Không mặc định đưa user ID, email hay mọi tenant ID động vào metric; cần kiểm soát cardinality và phạm vi dữ liệu. Event chi tiết có thể hỗ trợ điều tra với quyền truy cập phù hợp.

Mốc phát hành phần mềm, policy, cấu hình trust và luân chuyển khóa rất hữu ích để tìm lỗi tương quan. Giữ mã phiên bản và tham chiếu thay đổi thay vì ghi raw token, credential hoặc toàn bộ hồ sơ vào log.

## 13. Tình huống minh họa: nhiều node nhưng một miền quyết định

Một tổ chức có ba ứng dụng dùng IdP nhiều instance và một PDP từ xa. Một đợt đồng bộ thuộc tính tạo tải lớn lên database mà PDP và chức năng quản trị cùng sử dụng. Độ trễ PDP tăng; các service chờ quyết định và retry đồng thời.

Ban đầu, đội vận hành chỉ tăng số instance PDP. Tải truy vấn lên database tiếp tục tăng, không giải quyết được phụ thuộc chung. Trong khi đó, một số API fail closed và báo lỗi; các API xác minh token cục bộ với policy không cần truy vấn nguồn này vẫn có thể phục vụ theo hợp đồng của chúng.

Phân tích xác định miền sự cố là đường dữ liệu và tài nguyên chung giữa đánh giá quyền với đồng bộ. Biện pháp thiết kế gồm giới hạn tải batch, tách ngân sách/pool cho các hành trình, timeout có ngân sách, retry có giới hạn và bảo vệ phụ thuộc. Việc dùng cache chỉ được áp dụng cho những quyết định có điều kiện độ mới rõ ràng, không phải một nút chuyển sang allow khi timeout.

Sau khôi phục, nhóm kiểm tra cả quyền phải được phép và phải bị từ chối, tuổi dữ liệu cache, các yêu cầu thu hồi bị chậm và backlog đồng bộ. Không kết thúc điều tra chỉ vì CPU PDP đã giảm hoặc endpoint lại trả 200.

Tình huống cho thấy giới hạn phạm vi ảnh hưởng cần bắt đầu từ nguyên nhân chung và đường phụ thuộc thực tế, thay vì chỉ tăng số bản sao của thành phần nhìn thấy lỗi.

## 14. Các tình huống cần diễn tập trong thiết kế

| Tình huống | Điều cần chứng minh |
| --- | --- |
| Mất một instance hoặc node | Lưu lượng chuyển đúng và phần còn lại không bị quá tải dây chuyền |
| Mất một zone/region | Các phụ thuộc cần thiết và trạng thái ghi/đọc vẫn đáp ứng hợp đồng |
| PDP hoặc nguồn thuộc tính timeout | Không tự cấp quyền; chế độ suy giảm tuân thủ giới hạn |
| Khóa mới chưa tới cache của một nhóm API | Không chấp nhận nguồn khóa tùy ý; phạm vi lỗi được nhận diện |
| Policy sai được rollout | Có điều kiện dừng dựa trên tính đúng của quyền và phạm vi phát hành |
| Event thu hồi bị chậm hoặc giao lại | Không đánh dấu hoàn tất sớm, không khôi phục quyền từ sự kiện cũ |
| Một tenant/kết nối tạo tải bất thường | Các nhóm khác có tài nguyên và giới hạn bảo vệ phù hợp |
| Phục hồi snapshot cũ | Trạng thái thu hồi và trust đủ mới được áp dụng trước khi mở truy cập |
| IdP quản trị ngừng hoạt động | Đội có thẩm quyền vẫn sử dụng được đường phục hồi đã thiết kế |
| Pipeline audit/telemetry lỗi | Có quan sát và cách xử lý rõ cho mất bằng chứng hoặc đầy buffer |

Các diễn tập phải có phạm vi, điều kiện dừng, bằng chứng và phương án phục hồi phù hợp với môi trường. Mục tiêu là kiểm chứng thiết kế chịu lỗi, không thử tắt ngẫu nhiên hệ thống production mà chưa có kế hoạch.

Failure domain của IAM cần được xem ở cả hạ tầng, dữ liệu, trust, policy và vận hành. Khi biết nguyên nhân chung nào có thể tác động đến hành trình nào, kiến trúc mới có thể cô lập sự cố, tiếp tục những thao tác còn đủ điều kiện và phục hồi mà không mở lại quyền hoặc danh tính ngoài ý muốn.
