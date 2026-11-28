# Break-glass service account

## 1. Danh tính khẩn cấp để khôi phục một khả năng cụ thể

**Break-glass service account** là tài khoản dịch vụ được chuẩn bị cho những thao tác khôi phục khẩn cấp khi đường truy cập vận hành thông thường không còn đáp ứng được. Một công cụ hoặc tác vụ khôi phục có thể dùng danh tính này để thực hiện phạm vi hành động đã xác định trước, dưới sự kiểm soát của người chịu trách nhiệm xử lý sự cố.

Ví dụ, hệ thống triển khai thông thường dựa vào một dịch vụ liên kết danh tính đang ngừng hoạt động. Nhóm vận hành cần chạy công cụ khôi phục để đưa một cấu hình truy cập về bản đã xác minh. Nếu nền tảng đích hỗ trợ một đường xác thực khẩn cấp độc lập phù hợp, công cụ có thể dùng một service account đã được chuẩn bị cho đúng nhiệm vụ đó.

Mục tiêu là khôi phục dịch vụ hoặc đường quản trị hợp lệ trong một tình huống đã tính đến. Tài khoản này không nên trở thành credential dự phòng được nhúng vào mọi ứng dụng để sử dụng mỗi khi gặp lỗi xác thực.

Tên “break-glass” không mang lại đặc tính bảo mật riêng. Tài khoản chỉ có giá trị khi có thiết kế rõ về quyền, credential, điều kiện kích hoạt, người chịu trách nhiệm, audit và cách kết thúc truy cập sau sự cố.

## 2. Phân biệt ba loại truy cập

| Loại truy cập | Chủ thể thực hiện | Mục đích | Cách sử dụng mong đợi |
|---|---|---|---|
| Service account vận hành thông thường | Ứng dụng, job hoặc pipeline thường xuyên | Xử lý nghiệp vụ và vận hành hằng ngày | Được cấp credential theo đường chuẩn, giới hạn quyền theo chức năng |
| Tài khoản khẩn cấp của con người | Một người vận hành được xác định | Đăng nhập hoặc quản trị khẩn cấp | Theo quy trình xác thực, kích hoạt và truy vết cho người dùng |
| Break-glass service account | Công cụ hoặc tác vụ khôi phục | Thực hiện thao tác máy trong một tình huống khẩn cấp xác định | Được kích hoạt có kiểm soát, có owner và bằng chứng về người kích hoạt |

Một tài khoản người dùng được đặt tên `emergency-admin` không tự trở thành service account. Ngược lại, việc một người chạy công cụ bằng danh tính dịch vụ không làm mất trách nhiệm của người đó: hệ thống cần ghi được cả **ai cho phép hoặc khởi chạy** và **principal nào thực thi hành động**.

Nếu công cụ chỉ cần một người dùng khẩn cấp đăng nhập rồi thực hiện thao tác quản trị trực tiếp, không nhất thiết phải tạo thêm service account. Chọn loại danh tính theo chủ thể và cơ chế truy cập thực tế, thay vì tạo thêm tài khoản chỉ vì muốn có một lối dự phòng.

## 3. Khi nào mới cần dùng break-glass?

Điều kiện kích hoạt phải được mô tả bằng tình huống và ảnh hưởng cụ thể, không chỉ là “có lỗi”. Một số ví dụ:

- Đường liên kết danh tính hoặc cơ chế cấp credential thông thường không hoạt động, nhưng tài nguyên đích còn hỗ trợ một đường khôi phục đã chuẩn bị.
- Một thay đổi chính sách làm mất quyền của công cụ vận hành chính; cần thao tác khôi phục được giới hạn đến đúng chính sách hoặc tài nguyên đó.
- Sự cố ảnh hưởng kênh quản lý secret khiến tác vụ khôi phục không lấy được credential theo cách bình thường.
- Cần cô lập hoặc khôi phục một thành phần trọng yếu trong khi đường tự động hóa chính đang bị nghi chiếm quyền.

Các tình huống này chỉ là ứng viên. Việc một thành phần bị lỗi không tự chứng minh break-glass sẽ giải quyết được lỗi đó hoặc việc kích hoạt đã được cho phép.

| Tình huống | Cách đánh giá |
|---|---|
| Một ứng dụng thiếu một quyền mới | Thường cần quy trình thay đổi quyền thông thường; không mặc định là khẩn cấp |
| Credential của job hết hạn do bỏ sót rotation | Ưu tiên khôi phục qua đường quản lý credential chuẩn nếu còn hoạt động |
| Đường cấp token chính bị gián đoạn và ảnh hưởng phục hồi dịch vụ | Đánh giá đường khôi phục độc lập đã được chuẩn bị và điều kiện kích hoạt |
| Một lỗi mạng làm API không thể truy cập | Credential khẩn cấp không sửa được kết nối mạng; phải xác định đúng lớp lỗi |
| Một tài khoản thường bị từ chối vì vượt phạm vi dữ liệu | Không dùng break-glass để né quyết định phân quyền hợp lệ |

Break-glass không được dùng để bỏ qua thay đổi có kế hoạch, tránh sửa cấu hình sai hoặc giúp ứng dụng tiếp tục chạy với quyền quá rộng.

## 4. Thiết kế từ tình huống hỏng, không từ một role quản trị

Một lỗi thiết kế thường gặp là tạo sẵn tài khoản toàn quyền rồi gọi đó là phương án khẩn cấp. Cách này chưa trả lời được điều quan trọng nhất: tài khoản có còn dùng được khi đường bình thường hỏng không, và nó thực sự cần làm gì?

Nên bắt đầu từ ba câu hỏi:

1. Thành phần hoặc đường tin cậy nào có thể không hoạt động?
2. Thao tác tối thiểu nào giúp khôi phục đường chuẩn hoặc giảm ảnh hưởng sự cố?
3. Những phụ thuộc nào phải còn hoạt động để thực hiện thao tác đó?

Ví dụ, nếu tình huống dự kiến là federation bị gián đoạn, một service account vẫn phải dùng chính federation đó để nhận token không tạo ra đường khôi phục độc lập. Tương tự, lưu credential khẩn cấp trong kho secret đang là đối tượng cần khôi phục có thể tạo phụ thuộc vòng tròn.

| Phụ thuộc | Câu hỏi thiết kế |
|---|---|
| Xác thực người kích hoạt | Nếu IdP chính hỏng, người có trách nhiệm chứng minh thẩm quyền bằng cách nào? |
| Nơi giữ credential | Có lấy được credential khi kho secret chính không hoạt động không? |
| Khóa giải mã | Nếu bản credential được mã hóa, khóa giải mã có phụ thuộc cùng hệ thống đang hỏng không? |
| Bên xác thực tài khoản dịch vụ | Tài nguyên đích có còn chấp nhận phương thức khẩn cấp đó không? |
| Kết nối và công cụ | Có đường mạng, DNS, chứng thư và công cụ đáng tin cậy để truy cập không? |
| Ghi nhận và phê duyệt | Nếu hệ thống ticket hoặc audit chính hỏng, bằng chứng tạm thời được lưu thế nào? |

Độc lập phải gắn với từng tình huống hỏng, không có nghĩa tạo một hạ tầng hoàn toàn tách biệt khỏi mọi hệ thống. Một đường khôi phục cũng không thể giải quyết mọi dạng outage: nếu cả tài nguyên đích và cơ chế xác thực khẩn cấp của nó đều không hoạt động, cần phương án phục hồi khác.

Chỉ sử dụng cơ chế khôi phục mà nền tảng thực sự hỗ trợ và tổ chức đã kiểm soát. Không coi việc tắt xác thực, bỏ kiểm tra TLS hoặc tin một header do client tự khai là một cơ chế break-glass hợp lệ.

## 5. Quyền tối thiểu trong tình huống khẩn cấp

Least privilege vẫn áp dụng. Điểm khác là quyền được xác định từ **nhiệm vụ khôi phục**, không phải từ nhu cầu nghiệp vụ thường ngày của ứng dụng.

Một công cụ chỉ cần đưa một policy về bản đã xác minh có thể không cần quyền đọc toàn bộ dữ liệu khách hàng hoặc tạo thêm quản trị viên. Nếu nền tảng cho phép, giới hạn principal đến tài nguyên và thao tác khôi phục cần thiết.

Không nên để ứng dụng thường xuyên có quyền tự kích hoạt danh tính khẩn cấp hoặc đọc credential của nó. Nếu một lỗ hổng trong ứng dụng cho phép lấy ngay credential mạnh hơn, ranh giới giữa quyền runtime và quyền khôi phục gần như không còn.

Có hai mô hình cần cân nhắc theo cơ chế hệ thống:

- **Principal có quyền khôi phục được cấp sẵn:** giảm phụ thuộc vào việc phải cấp quyền khi xảy ra sự cố, nhưng cần bảo vệ chặt khả năng lấy và sử dụng credential.
- **Principal chỉ nhận quyền hoặc credential khi kích hoạt:** giảm thời gian đặc quyền có thể được sử dụng, nhưng cơ chế kích hoạt phải còn hoạt động trong tình huống hỏng dự kiến.

Không mặc định giải pháp just-in-time là đủ nếu nó cần chính dịch vụ IAM đang mất khả năng phục vụ. Ngược lại, việc chuẩn bị sẵn một tài khoản cũng không biện minh cho quyền không giới hạn và credential dễ lấy.

Nếu một hệ thống chỉ cung cấp đường phục hồi với quyền rất rộng, phải hiểu rõ phạm vi ảnh hưởng đó và tăng kiểm soát ở nơi khác: người được kích hoạt, nơi chạy công cụ, thời gian sử dụng, hành động đã chuẩn bị và giám sát. Không mô tả một principal là “ít quyền” khi nền tảng thực tế không giới hạn được nó như mong muốn.

## 6. Bảo vệ credential và quyền kích hoạt

Credential khẩn cấp cần đủ khả dụng cho tình huống đã thiết kế, đồng thời khó bị truy cập ngoài quy trình. Phương án có thể gồm kho lưu trữ độc lập phù hợp, bản mã hóa được bảo quản có kiểm soát hoặc cơ chế phần cứng. Cách chọn phụ thuộc khả năng của nền tảng và các phụ thuộc cần tránh.

Một bản mã hóa chỉ an toàn và hữu ích khi có quản lý khóa phù hợp. Đặt credential và khóa giải mã ở cùng vị trí có thể không tạo được bảo vệ mong muốn; đặt khóa ở một hệ thống không truy cập được khi sự cố xảy ra lại làm mất khả năng phục hồi.

Kiểm soát tối thiểu cần làm rõ:

- Ai có quyền yêu cầu, cho phép và thực hiện kích hoạt.
- Ai được lấy hoặc sử dụng credential, qua công cụ nào.
- Credential có bị lộ cho người vận hành hay được cấp trực tiếp cho môi trường thực thi.
- Điều kiện nào làm yêu cầu bị từ chối và cách xử lý khi kênh phê duyệt chính không hoạt động.
- Những sự kiện nào phải tạo cảnh báo và bên nào nhận cảnh báo.
- Khi nào credential hết hiệu lực, bị thu hồi hoặc phải thay sau sử dụng.

Có thể áp dụng kiểm soát hai người cho các thao tác nhạy cảm nếu quy trình vẫn đáp ứng được tình huống khẩn cấp đã đặt ra. Không nên yêu cầu một bước phê duyệt mà tất cả người hoặc hệ thống thực hiện bước đó đều không thể truy cập trong tình huống hỏng dự kiến. Mọi cơ chế thay thế phải được xác định trước, có trách nhiệm và bằng chứng rõ ràng.

Break-glass không mặc định đồng nghĩa bỏ MFA cho con người. Nếu một phương thức xác thực thông thường phụ thuộc thành phần đang hỏng, cần thiết kế phương thức khẩn cấp thích hợp cho người kích hoạt. Đường khôi phục cho máy và việc xác minh thẩm quyền con người là hai phần liên quan nhưng không thay thế nhau.

## 7. Từ trạng thái dự phòng đến kết thúc sử dụng

```mermaid
flowchart LR
    A[Đã chuẩn bị và kiểm thử] --> B[Xác nhận tình huống và thẩm quyền]
    B --> C[Cấp khả năng sử dụng có giới hạn]
    C --> D[Chạy thao tác khôi phục]
    D --> E[Khôi phục đường vận hành chuẩn]
    E --> F[Thu hồi truy cập và đối chiếu audit]
    F --> G[Đưa về trạng thái sẵn sàng có kiểm soát]
```

### 7.1. Chuẩn bị trước sự cố

Ghi owner, principal ID, môi trường, tình huống được phép dùng, quyền, phụ thuộc, cách kiểm thử và người giữ khả năng kích hoạt. Chuẩn bị công cụ hoặc runbook để tránh phải sáng tác thao tác có đặc quyền cao trong lúc áp lực.

Credential không được nhúng vào runbook hoặc repository chứa công cụ. Tài liệu chỉ định cách lấy qua kênh đã kiểm soát, không ghi giá trị bí mật.

### 7.2. Xác nhận kích hoạt

Xác định sự cố, mức ảnh hưởng, vì sao đường chuẩn không đáp ứng và thao tác dự kiến. Gắn mã sự cố hoặc một định danh tạm thời có thể đối chiếu sau. Xác định người chịu trách nhiệm và thẩm quyền theo quy trình đã chuẩn bị.

Đặt thời hạn sử dụng và giới hạn tài nguyên. Nếu nền tảng không tự thực thi được thời hạn, phải có cơ chế điều phối và thu hồi tương ứng; một dòng “hết hạn sau sự cố” trong ticket không tự làm credential mất hiệu lực.

### 7.3. Thực thi trong môi trường đáng tin cậy

Chạy công cụ được xác minh từ một môi trường được kiểm soát. Chỉ phân phối credential cho nơi cần dùng và trong thời gian cần thiết. Không đưa nó vào pipeline thường xuyên đang bị nghi chiếm quyền hoặc vào máy cá nhân không phù hợp với quy trình.

Ghi nhận hành động, tài nguyên và kết quả mà không ghi token, mật khẩu hay khóa riêng. Nếu hệ thống log chính đang hỏng, dùng cơ chế lưu bằng chứng tạm thời đã chuẩn bị, bảo vệ tính toàn vẹn và đồng bộ lại khi khôi phục.

### 7.4. Khôi phục đường chuẩn và dừng đường khẩn cấp

Kiểm tra người dùng, workload và công cụ vận hành thông thường đã truy cập đúng trở lại. Dừng execution khẩn cấp và ngăn các job hoặc cấu hình tạm tiếp tục dùng danh tính đó.

Thu hồi credential tạm, bỏ quyền được cấp khi kích hoạt hoặc khóa lại khả năng sử dụng theo thiết kế. Đối với credential dài hạn đã được đưa ra sử dụng, thực hiện thay thế hoặc thu hồi phù hợp trước khi đưa tài khoản về trạng thái dự phòng.

Đánh giá cả token và phiên đã cấp. Vô hiệu hóa một secret có thể chỉ chặn lần lấy token tiếp theo; nó không bảo đảm token cũ hoặc kết nối đang mở lập tức bị chặn. Cần kiểm tra cách tài nguyên đích thực thi thời hạn, thu hồi và quyền hiện hành.

### 7.5. Đối chiếu và tái lập khả năng phục hồi

Đối chiếu hành động thực tế với phạm vi được cho phép, xác nhận không còn grant tạm hoặc credential phân phối ngoài ý muốn. Nếu có thay đổi ngoài kế hoạch, phải xử lý và ghi rõ, không chỉ đóng ticket vì hệ thống đã hoạt động.

Sau khi thu hồi credential cũ, xác minh phương án khẩn cấp vẫn sẵn sàng cho lần sau: credential dự phòng hợp lệ, owner còn đúng, công cụ và tài liệu đã cập nhật. Không khôi phục tính sẵn sàng bằng cách bật lại credential nghi bị lộ.

## 8. Ví dụ: khôi phục một cấu hình truy cập cho hệ thống Java

Giả sử nhóm vận hành quản lý dịch vụ Java `billing-api`. Pipeline thông thường lấy token qua một đường federation để triển khai cấu hình. Một thay đổi cấu hình làm mất quyền cần thiết của pipeline. API quản lý đích vẫn hoạt động và hỗ trợ đường khôi phục độc lập đã được chuẩn bị.

Nhóm có một công cụ khôi phục với service account `billing-policy-recovery-prod`. Công cụ chỉ nhằm khôi phục một cấu hình truy cập đã xác minh trong phạm vi tài nguyên được giao. Nó không phải danh tính runtime của `billing-api` và không được gắn vào container đang phục vụ khách hàng.

Thông tin chuẩn bị có thể mô tả như sau. Đây là mô hình minh họa, không phải schema của một nền tảng cụ thể:

```yaml
principal: billing-policy-recovery-prod
owner: platform-recovery-team
environment: production
purpose: Restore the approved access configuration
activation:
  incident_reference: required
  accountable_operator: required
  authorized_scope: required
  usage_deadline: required
evidence:
  record_activation: true
  record_actions_and_results: true
  record_credentials: false
closure:
  normal_access_verified: required
  emergency_access_revoked: required
  temporary_changes_reconciled: required
```

Trình tự sử dụng là xác nhận sự cố và phạm vi, kích hoạt qua kênh đã chuẩn bị, chạy công cụ khôi phục, kiểm tra pipeline thường xuyên hoạt động rồi thu hồi khả năng truy cập khẩn cấp. Nếu nền tảng thực tế không giới hạn principal đến đúng thao tác mong muốn, hồ sơ phải ghi nhận phạm vi quyền thực và áp dụng kiểm soát tương ứng.

Một thiết kế sai là đặt secret khẩn cấp trong cấu hình `billing-api` và viết fallback như sau:

```text
nếu yêu cầu thông thường bị từ chối:
    đổi sang credential khẩn cấp
    gửi lại cùng yêu cầu
```

Fallback này biến mọi lỗi xác thực hoặc phân quyền thành cơ hội sử dụng đặc quyền cao hơn. Nó cũng đưa credential khôi phục vào cùng phạm vi bị chiếm khi ứng dụng có lỗ hổng.

Thiết kế phù hợp là để ứng dụng báo lỗi rõ ràng và giữ ranh giới quyền; quy trình sự cố quyết định việc khởi chạy một tác vụ khôi phục riêng, với danh tính, môi trường và phạm vi được kiểm soát. Không biến break-glass thành một nhánh nghiệp vụ tự động trong mọi request.

## 9. Audit phải nối được hành động máy với trách nhiệm con người

Audit chỉ ghi “service account recovery đã cập nhật policy” thường chưa đủ. Cần nối được chuỗi sự kiện từ kích hoạt đến kết thúc:

| Dữ liệu bằng chứng | Mục đích |
|---|---|
| Mã sự cố, tình huống hỏng và phạm vi | Giải thích vì sao đường khẩn cấp được sử dụng |
| Người kích hoạt và người cho phép theo quy trình | Xác định trách nhiệm và thẩm quyền |
| Principal ID, môi trường, credential ID nếu có | Xác định chính xác danh tính đã được dùng mà không giữ secret |
| Execution ID, công cụ hoặc artifact đã xác minh | Truy nguồn lần chạy và nội dung thực thi |
| Thao tác, tài nguyên, thời điểm, kết quả | Đối chiếu quyền thực tế với phạm vi được phép |
| Thời điểm thu hồi và kiểm chứng | Chứng minh quyền khẩn cấp không còn được sử dụng ngoài cửa sổ |

Cảnh báo nên bao phủ việc đọc hoặc cấp credential, phát hành credential dẫn xuất, sử dụng principal và thay đổi quyền của tài khoản. Nếu chỉ cảnh báo khi một API ghi dữ liệu bị gọi, có thể bỏ qua việc credential đã bị lấy hoặc đặc quyền đã bị thay đổi trước đó.

Không dùng địa chỉ IP hoặc một request ID tự khai làm bằng chứng duy nhất về người kích hoạt. Cần đối chiếu các nguồn xác thực và audit có độ tin cậy phù hợp. Khi backfill bằng chứng sau outage, giữ rõ thời điểm sự kiện gốc và thời điểm nhập lại, tránh tạo ấn tượng rằng hệ thống trung tâm đã ghi nhận theo thời gian thực.

## 10. Kiểm thử khả năng phục hồi và giới hạn quyền

Một tài khoản chưa từng được kiểm thử có thể không dùng được đúng lúc cần: credential hết hạn, trust bị thay, owner không còn quyền lấy, công cụ thiếu dependency hoặc đường mạng chỉ tồn tại trên sơ đồ.

Kiểm thử có kiểm soát nên bao gồm:

- Mô phỏng đúng phụ thuộc bị hỏng và xác minh đường khẩn cấp không cần nó.
- Xác minh người được giao trách nhiệm lấy hoặc sử dụng được credential theo quy trình.
- Kiểm tra thao tác cần thiết thành công và hành động ngoài phạm vi bị từ chối khi nền tảng hỗ trợ giới hạn đó.
- Kiểm tra cảnh báo, audit và đường lưu bằng chứng khi thành phần trung tâm không hoạt động.
- Kiểm tra việc kết thúc execution, thu hồi credential hoặc quyền tạm và xử lý phiên còn tồn tại.
- Xác minh phương án lại ở trạng thái sẵn sàng sau khi hoàn tất bài kiểm thử.

Ưu tiên môi trường thử nghiệm và thao tác không phá hủy phù hợp. Việc xác minh một đường quản trị production cần có phạm vi và kế hoạch tương ứng; không thực hiện thay đổi gây gián đoạn chỉ để chứng minh credential có quyền mạnh.

Thay đổi IdP, kho secret, chính sách mạng, owner hoặc hệ thống triển khai đều có thể làm phương án khẩn cấp mất hiệu lực. Cần rà soát theo các thay đổi này, không chỉ theo lịch cố định.

## 11. Những sai lầm cần tránh

| Sai lầm | Vấn đề tạo ra | Hướng xử lý |
|---|---|---|
| Dùng principal khẩn cấp cho tác vụ hằng ngày | Đặc quyền trở thành trạng thái vận hành mặc định | Tách đường chuẩn và đường khôi phục, rà soát mọi lần sử dụng |
| Giữ credential trong hệ thống cần được khôi phục | Không lấy được credential khi sự cố xảy ra | Kiểm tra phụ thuộc và chuẩn bị kênh phù hợp với tình huống hỏng |
| Cho runtime đọc credential khẩn cấp | Lỗ hổng ứng dụng có thể mở rộng sang quyền khôi phục | Tách khả năng lấy credential và môi trường thực thi |
| Cấp toàn quyền vì “khẩn cấp” | Tăng phạm vi thiệt hại và khó đối chiếu hành động | Xác định thao tác khôi phục tối thiểu và quyền thực tế |
| Tự fallback khi nhận lỗi từ chối | Bỏ qua ranh giới xác thực, phân quyền | Kích hoạt qua quy trình sự cố riêng có thẩm quyền |
| Không ghi người kích hoạt | Không nối được hành động máy với trách nhiệm | Lưu chuỗi kích hoạt, execution và hành động |
| Hết sự cố nhưng giữ phiên hoặc grant tạm | Đặc quyền vẫn tiếp tục tồn tại | Đặt điều kiện đóng việc dựa trên thu hồi và kiểm chứng |
| Thu hồi rồi quên tái lập phương án dự phòng | Không còn khả năng khôi phục cho lần sau | Xác minh trạng thái sẵn sàng với credential an toàn |

Break-glass service account là một phần của thiết kế khả năng phục hồi IAM. Nó phải giải quyết được tình huống hỏng cụ thể, giới hạn được quyền hoặc có kiểm soát bù phù hợp, cho phép truy vết người chịu trách nhiệm và kết thúc được truy cập sau sử dụng. Tài khoản khẩn cấp chỉ hoàn thành vai trò khi đường vận hành chuẩn được khôi phục và đặc quyền tạm thời đã được thu hồi có bằng chứng.
