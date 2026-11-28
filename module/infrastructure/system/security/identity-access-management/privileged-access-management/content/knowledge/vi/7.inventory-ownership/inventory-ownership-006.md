# Associated credential

Trong inventory của hệ thống quản lý truy cập đặc quyền (Privileged Access Management — PAM), biết một tài khoản tồn tại chưa đủ để quản lý an toàn việc sử dụng nó. Cần biết tài khoản xác thực bằng phương tiện nào, credential được lưu hoặc quản lý ở đâu, dịch vụ nào đang sử dụng và ai chịu trách nhiệm khi phải luân chuyển hoặc thu hồi.

**Associated credential** trong bài này được hiểu là credential được liên kết với một danh tính, tài nguyên hoặc mục đích sử dụng đã xác định trong inventory. Tùy sản phẩm, trường hoặc đối tượng mang tên này có thể có cách triển khai khác nhau; điều quan trọng là biểu diễn đúng quan hệ và vòng đời, không chỉ ghi một chuỗi tên credential.

Trong chương **Inventory và ownership**, liên kết này giúp quản lý tài khoản quản trị, tài khoản dịch vụ và danh tính hạ tầng nhạy cảm xuyên suốt quá trình kiểm kê, cấp quyền tối thiểu, JIT/JEA, lưu trong vault khi phù hợp, luân chuyển, giám sát và thu thập bằng chứng kiểm toán.

## 1. Phân biệt danh tính, credential và quyền

Ba khái niệm thường đi cùng nhau nhưng có vai trò khác nhau:

| Khái niệm | Câu hỏi cần trả lời | Ví dụ |
| --- | --- | --- |
| Danh tính hoặc principal | Hệ thống đang xác thực ai? | Tài khoản quản trị, service account, service principal, danh tính workload |
| Credential | Bằng chứng hoặc cơ chế xác thực nào được dùng? | Mật khẩu, khóa SSH, chứng thư kèm khả năng sử dụng khóa riêng, API key, token |
| Quyền | Sau xác thực, danh tính được làm gì và trên đâu? | Khởi động lại dịch vụ, đọc dữ liệu, quản lý policy trong scope cụ thể |

Liên kết một credential với tài khoản không tự cấp quyền mới cho tài khoản đó. Ngược lại, một credential của danh tính mạnh vẫn có tác động lớn dù bản ghi inventory chỉ hiển thị một tên đơn giản.

Một người có thể đăng nhập PAM bằng danh tính cá nhân, được duyệt một tác vụ, rồi PAM sử dụng credential của tài khoản đích để thực hiện tác vụ. Cần giữ riêng người yêu cầu, danh tính thực thi và credential được dùng để có thể truy vết đầy đủ.

### 1.1. Loại dữ liệu nào là credential

| Loại | Thành phần cần quản lý | Điểm cần phân biệt |
| --- | --- | --- |
| Mật khẩu tài khoản | Bí mật và phiên bản hiện hành ở nơi quản lý phù hợp | Tên tài khoản không phải mật khẩu |
| Khóa SSH | Khóa riêng hoặc cơ chế sử dụng khóa; quan hệ với khóa công khai được chấp nhận | Chỉ có public key chưa đủ để xác thực như bên giữ private key |
| Chứng thư dùng xác thực | Chứng thư, danh tính được chứng thực và nơi thực hiện thao tác bằng khóa riêng | Chứng thư công khai không đồng nghĩa khóa riêng được phép xuất ra |
| API key hoặc client secret | Vật liệu bí mật, định danh key và điều kiện sử dụng | Client ID thường là định danh, không thay thế client secret |
| Access token hoặc refresh token | Loại token, nơi cấp, đối tượng nhận, thời hạn và cơ chế thu hồi | Hai loại token có vòng đời và khả năng sử dụng khác nhau |
| Danh tính liên kết hoặc credential ngắn hạn | Quan hệ tin cậy, nguồn cấp và điều kiện phát hành | Không nhất thiết có một bí mật dài hạn để lưu trong vault |

Một số khóa được giữ trong HSM hoặc cơ chế phần cứng và không xuất được. Inventory nên tham chiếu tới khóa và quyền sử dụng nó, không yêu cầu sao chép vật liệu khóa chỉ để hoàn thiện bản ghi.

Với workload sử dụng danh tính được nền tảng quản lý, mục tiêu kiểm kê là biết cách workload nhận và dùng thông tin xác thực. Không tạo thêm mật khẩu tĩnh chỉ vì mẫu inventory có trường credential.

## 2. Mô hình hóa quan hệ liên kết

Một mô hình đơn giản có thể thể hiện như sau:

```text
Người vận hành --yêu cầu tác vụ qua--> PAM
PAM hoặc workload --sử dụng--> Credential
Credential --xác thực cho--> Principal
Principal --có quyền trên--> Tài nguyên đích
Credential --được quản lý tại--> Vault / nền tảng cấp / phần cứng bảo vệ khóa
Chủ quản --chịu trách nhiệm về--> Principal và vòng đời sử dụng credential
```

Đây là những loại quan hệ khác nhau. Người được phép yêu cầu một phiên quản trị không mặc nhiên được xem mật khẩu của tài khoản đích. Người quản lý metadata cũng không mặc nhiên được giải mã bí mật hoặc sửa quyền của principal.

### 2.1. Quan hệ nhiều-nhiều

Một principal có thể có nhiều credential: hai API key trong giai đoạn chuyển đổi, nhiều chứng thư hoặc nhiều khóa SSH. Một credential cũng có thể đang được nhiều consumer sử dụng, chẳng hạn hai instance ứng dụng và một tác vụ theo lịch.

Cần mô hình hóa riêng:

- Principal được credential xác thực cho.
- Tài nguyên hoặc dịch vụ chấp nhận credential.
- Workload, ứng dụng hoặc công cụ thực sự sử dụng credential.
- Nơi quản lý và phiên bản vật liệu xác thực.
- Quan hệ phụ thuộc cần cập nhật khi credential thay đổi.

Hai máy chủ có tài khoản cục bộ cùng tên vẫn có thể là hai principal khác nhau. Không ghép credential chỉ theo username hoặc tên dịch vụ. Cần có định danh nguồn, môi trường, tenant/domain hoặc máy đích phù hợp.

Việc nhiều tài khoản tình cờ dùng cùng một mật khẩu cũng không biến chúng thành một danh tính dùng chung hợp lệ. Đó là vấn đề tái sử dụng bí mật cần được đánh giá riêng, không phải lý do hợp nhất inventory theo giá trị bí mật.

### 2.2. Credential xác thực cho tài khoản và credential hỗ trợ quản trị

Một quy trình PAM có thể cần một credential để đăng nhập tài khoản đích, một danh tính khác để đổi mật khẩu hoặc một tài khoản phục hồi khi mất đồng bộ. Các liên kết này cần ghi rõ mục đích.

Không coi credential dùng để luân chuyển hoặc khôi phục là credential của chính tài khoản đích. Chúng có thể thuộc principal khác và có quyền mạnh hơn. Cần kiểm kê phạm vi quyền, chủ quản và phụ thuộc của từng principal.

Nếu mọi credential đều phụ thuộc vào một tài khoản hỗ trợ duy nhất, tài khoản đó có thể trở thành điểm ảnh hưởng lớn. Quan hệ quản trị ngược hoặc vòng phụ thuộc cũng cần được nhận diện để tránh tình huống mất khả năng luân chuyển khi một credential hết hiệu lực.

## 3. Metadata nên có trong inventory

Bản ghi inventory nên lưu thông tin liên kết và quản trị; vật liệu bí mật được bảo vệ bằng cơ chế chuyên dụng phù hợp.

| Nhóm thông tin | Nội dung gợi ý | Mục đích |
| --- | --- | --- |
| Định danh | Credential ID nội bộ, ID nguồn, loại credential | Phân biệt đối tượng và đối chiếu qua các hệ thống |
| Principal | ID tài khoản, tenant/domain, loại danh tính | Xác định credential xác thực cho ai |
| Phạm vi | Tài nguyên chấp nhận, môi trường, ứng dụng | Tránh dùng nhầm giữa production và môi trường khác |
| Mục đích | Đăng nhập, runtime, triển khai, luân chuyển hoặc phục hồi | Phân biệt vai trò của các credential liên quan |
| Nơi quản lý | Tham chiếu secret, key handle hoặc nguồn cấp danh tính | Tìm đúng nơi quản lý mà không sao chép bí mật |
| Phiên bản | ID phiên bản hoặc metadata key tương ứng khi có | Truy vết giai đoạn chuyển đổi |
| Consumer | Workload, instance, tác vụ theo lịch, công cụ vận hành | Đánh giá phụ thuộc và tác động luân chuyển |
| Ownership | Chủ quản chịu trách nhiệm, nhóm vận hành, đầu mối dự phòng | Biết ai quyết định và ai thực hiện |
| Vòng đời | Trạng thái, thời hạn, lần xác minh hoặc luân chuyển gần nhất | Phát hiện quá hạn hoặc chưa hoàn tất chuyển đổi |
| Kiểm soát | Chính sách truy xuất, phê duyệt, phiên PAM và log liên quan | Kiểm soát sử dụng và lưu bằng chứng |

Tham chiếu logic tới một secret và tham chiếu phiên bản có mục đích khác nhau. Một consumer có thể lấy phiên bản được đánh dấu hiện hành hoặc bị ghim vào phiên bản cụ thể. Inventory phải phản ánh cách sử dụng thực tế, vì cập nhật phiên bản hiện hành trong vault chưa chắc làm consumer đổi theo.

Không dùng giá trị mật khẩu, token, private key hoặc bản mã bí mật sao chép từ nơi khác làm trường định danh. Cũng không tạo hash mật khẩu để so khớp credential trong inventory: việc đó tạo thêm dữ liệu nhạy cảm và có thể gây rủi ro dò đoán ngoại tuyến.

## 4. Gán ownership cho liên kết credential

Ownership cần thể hiện trách nhiệm thực tế, không chỉ một địa chỉ email được điền vào biểu mẫu.

| Vai trò | Trách nhiệm chính |
| --- | --- |
| Chủ quản danh tính hoặc dịch vụ | Xác nhận nhu cầu tồn tại, phạm vi sử dụng và quyết định ngừng dùng |
| Chủ workload sử dụng | Xác định consumer, cách nhận credential, cập nhật và xác minh sau thay đổi |
| Đội vận hành PAM hoặc vault | Quản lý cơ chế lưu, cấp phát, luân chuyển và bằng chứng theo phân quyền |
| Chủ hệ thống đích | Xác nhận phương thức xác thực, quyền và khả năng vô hiệu hóa credential |
| Bộ phận quản trị chính sách | Xác định điều kiện sử dụng, ngoại lệ, rà soát và phân tách nhiệm vụ |

Một tổ chức có thể gộp một số vai trò, nhưng phải giữ rõ ai quyết định, ai thực hiện và ai xác minh. Không mặc định người tạo bản ghi trở thành chủ quản lâu dài.

Việc gán owner trong inventory không tự cấp quyền truy xuất bí mật. Khi đổi owner hoặc nhóm vận hành, quyền vào vault, quyền quản trị ở đích và quyền yêu cầu phiên cần được rà soát theo quy trình riêng.

Với tài khoản dịch vụ, nên có đầu mối là nhóm chịu trách nhiệm vận hành và cơ chế tìm người đang trực. Khi người phụ trách chuyển việc, ownership phải được bàn giao mà không làm mất lịch sử hoặc phụ thuộc ứng dụng.

Nếu chưa xác nhận được owner, ghi trạng thái cần xác minh và ưu tiên theo tác động. Không tự xóa credential của một dịch vụ đang chạy chỉ vì trường owner còn trống.

## 5. Xác minh một association có đúng hay không

Một liên kết chỉ dựa trên tên secret gần giống tên tài khoản có độ tin cậy thấp. Cần đối chiếu nhiều nguồn:

1. **Danh tính:** credential được phát hành hoặc cấu hình cho principal nào, trong tenant/domain hay hệ thống nào.
2. **Đích xác thực:** tài nguyên hoặc dịch vụ nào chấp nhận credential và bằng cơ chế nào.
3. **Nơi quản lý:** tham chiếu có trỏ đúng đối tượng, môi trường và phiên bản hay không.
4. **Consumer:** workload nào tham chiếu credential, có cache hoặc ghim phiên bản không.
5. **Ownership:** chủ quản đã xác nhận mục đích và các phụ thuộc hay chưa.
6. **Hiệu lực:** trạng thái tại nơi cấp hoặc đích xác thực có khớp với inventory không.

Có thể thu thập bằng chứng từ metadata của vault, cấu hình tham chiếu của ứng dụng, khai báo triển khai, pipeline, danh tính workload và log sử dụng được phép. Không cần sao chép nội dung secret vào tập dữ liệu discovery.

Nếu cần xác minh xác thực thực tế, thực hiện trong phạm vi được cho phép bằng thao tác tối thiểu, có khả năng nhận diện đúng principal và không làm thay đổi nghiệp vụ. Không suy ra một credential có quyền quản trị chỉ vì xác thực thành công; quyền sau xác thực phải được đánh giá riêng.

### 5.1. Ghi nhận độ tin cậy và dữ liệu thiếu

Nên phân biệt các trạng thái như đã xác nhận, mới suy ra từ cấu hình và chưa xác minh. Một consumer không xuất hiện trong log có thể chưa chạy trong khoảng quan sát hoặc log chưa bao phủ đầy đủ.

Việc xóa credential khỏi cấu hình một instance cũng chưa chứng minh toàn bộ hệ thống đã ngừng dùng. Còn có thể có instance khác, tác vụ theo lịch, bản triển khai cũ hoặc công cụ phục hồi đang giữ tham chiếu.

Thời điểm “last rotated” chỉ có giá trị khi biết nó phản ánh thao tác nào. Một pipeline đã cập nhật metadata không chứng minh mật khẩu ở đích đã đổi hoặc mọi consumer đã nhận phiên bản mới.

### 5.2. Ví dụ metadata liên kết

Đoạn YAML dưới đây minh họa một mô hình nội bộ. Các định danh đều là ví dụ và không phải schema của một sản phẩm PAM cụ thể.

```yaml
credential_id: cred-payments-db-prod-01
principal_ref: principal-svc-payments-db-prod
authentication_method: password
purpose: application-runtime
environment: production
target_ref: database-payments-prod
storage_ref:
  type: vault
  secret_id: secret-payments-db-prod
  version_mode: current
owner_team_ref: team-payments-platform
consumers:
  - workload_ref: payments-api
    delivery_mode: runtime-secret-reference
  - workload_ref: payments-nightly-job
    delivery_mode: deployment-secret-reference
lifecycle_state: active
association_state: confirmed
```

Bản ghi không chứa mật khẩu. Hai consumer có cách nhận credential khác nhau; việc chuyển phiên bản có thể cần hai quy trình cập nhật khác nhau. Các ID tham chiếu cần trỏ tới đối tượng có thông tin cụ thể và được kiểm soát trong inventory thực tế.

Trong một mô hình dùng danh tính workload ngắn hạn, bản ghi có thể tham chiếu nguồn cấp và chính sách phát hành thay cho `storage_ref` kiểu vault. Không dùng một giá trị giả trong trường secret chỉ để làm cho mọi loại danh tính có cùng hình thức.

## 6. Luân chuyển theo đồ thị phụ thuộc

Associated credential giúp trả lời câu hỏi quan trọng trước khi luân chuyển: đổi credential này sẽ ảnh hưởng tới những principal, tài nguyên và consumer nào?

### 6.1. Chuẩn bị

Trước thay đổi, cần xác nhận owner, phương thức xác thực, cơ chế cập nhật tại đích, tất cả consumer đã biết, thời điểm tác vụ định kỳ chạy và khả năng kiểm tra sức khỏe ứng dụng.

Cần biết đích hỗ trợ nhiều credential cùng lúc hay chỉ một credential hiện hành. Có hệ thống cho phép chồng lấn key cũ và mới trong giai đoạn chuyển tiếp; có hệ thống đổi mật khẩu sẽ làm credential cũ không còn dùng được cho lần xác thực mới ngay theo cơ chế của nó.

Không áp dụng một thứ tự chung như “luôn ghi vault trước” hoặc “luôn đổi ở đích trước” cho mọi backend. Trình tự phải phù hợp với khả năng của đích, cách consumer nhận secret và kế hoạch xử lý mất đồng bộ.

### 6.2. Áp dụng và chuyển consumer

Một luồng tổng quát có thể gồm:

1. Tạo kế hoạch thay đổi và ghi nhận credential cùng phiên bản đang dùng.
2. Tạo hoặc cập nhật credential theo cơ chế được hệ thống đích hỗ trợ.
3. Cập nhật nơi quản lý và phân phối theo trình tự đã thiết kế.
4. Chuyển từng consumer sang phiên bản mới, có kiểm soát cache, kết nối và tiến trình.
5. Xác minh danh tính, kết nối và chức năng nghiệp vụ cần thiết.
6. Thu hồi credential cũ khi các điều kiện chuyển đổi đã đạt.
7. Kiểm tra credential cũ không còn được chấp nhận cho mục đích đã thu hồi và cập nhật bằng chứng.

Các bước này có thể cần phối hợp khác nhau giữa các backend. Nếu đích và vault không có giao dịch chung, phải có trạng thái chuyển đổi, cơ chế đối soát và xử lý khi một bên thành công còn bên kia lỗi.

### 6.3. Không đánh đồng đổi secret với hoàn tất luân chuyển

Nếu ứng dụng giữ credential trong bộ nhớ hoặc pool kết nối, cập nhật vault không tự làm nó nhận secret mới. Một tác vụ chạy mỗi đêm có thể chỉ lộ lỗi vào lần thực thi sau.

Tương tự, một kết nối đã xác thực có thể còn tồn tại sau khi mật khẩu đổi. Với khóa SSH, bỏ public key khỏi nơi chấp nhận khóa không tự đóng mọi phiên đã mở. Việc thu hồi token hoặc credential khác cũng cần dựa vào cơ chế thực tế của nền tảng.

Tiêu chí hoàn tất nên bao gồm consumer đã chuyển, hoạt động hợp lệ được xác minh, credential cũ bị vô hiệu hóa theo yêu cầu và các phiên hoặc token còn tồn tại được xử lý hoặc quản lý rõ ràng.

Nếu phải quay lui, không mặc định có thể phục hồi credential cũ đã bị thu hồi hoặc nghi bị lộ. Có thể cần phát hành credential khác, cập nhật lại consumer và tiếp tục đối soát. Quyết định phải cân bằng phục hồi dịch vụ với trạng thái an ninh hiện tại.

## 7. Liên kết với least privilege, JIT và JEA

Quyền xem metadata, quyền sử dụng credential và quyền đọc giá trị bí mật nên được phân biệt. Một người có thể được phép yêu cầu khởi động lại dịch vụ mà không cần biết mật khẩu của service account.

Với phiên do PAM điều phối, cần ràng buộc credential với đúng principal, tài nguyên và tác vụ được duyệt. Không để một credential dành cho môi trường thử nghiệm được tự chuyển sang production vì cùng tên tài khoản hoặc cùng nhãn ứng dụng.

JIT giới hạn thời gian được phép sử dụng quyền, còn JEA giới hạn hành động. Nếu người dùng được xem một bí mật dài hạn trong cửa sổ JIT, việc hết cửa sổ không làm người đó quên bí mật hoặc tự làm bí mật mất hiệu lực tại đích.

Vì vậy, cần xác định riêng:

- Người dùng có được nhận giá trị bí mật hay chỉ được PAM thực hiện tác vụ bằng credential.
- Credential có thể được dùng trực tiếp ngoài đường truy cập được quản lý hay không.
- Thời hạn và khả năng thu hồi ở đích có khớp với yêu cầu truy cập không.
- Phiên hoặc token được tạo ra có còn sống sau khi quyền JIT kết thúc không.

Với token ngắn hạn, không nhất thiết tạo một bản ghi inventory thủ công cho từng token được phát hành. Có thể quản lý nguồn cấp, danh tính, audience, chính sách phát hành và cơ chế liên kết log theo mô hình phù hợp. Giá trị token không cần xuất hiện trong inventory để truy vết.

Refresh token hoặc credential dùng để cấp token khác là một phụ thuộc quan trọng. Thu hồi nguồn cấp không bảo đảm mọi token đã phát hành đều mất hiệu lực ngay; cần kiểm tra thời hạn và cơ chế đánh giá hoặc thu hồi tương ứng.

## 8. Theo dõi trạng thái liên kết và thu hồi

Trạng thái inventory cần phản ánh mức xác minh, không chỉ ý định của người thao tác. Có thể định nghĩa các trạng thái nội bộ như sau:

| Trạng thái minh họa | Ý nghĩa |
| --- | --- |
| Đã phát hiện | Có bằng chứng về credential hoặc tham chiếu, chưa đủ thông tin liên kết |
| Đã xác nhận association | Đã xác minh principal, mục đích, nơi quản lý và owner trong phạm vi biết được |
| Đang sử dụng | Có hiệu lực hoặc được sử dụng theo bằng chứng tại thời điểm quan sát |
| Đang chuyển đổi | Các phiên bản hoặc consumer đang trong quá trình luân chuyển |
| Chờ xác minh thu hồi | Có quyết định ngừng dùng nhưng chưa đủ bằng chứng ở đích |
| Đã xác minh thu hồi | Đã xác nhận vô hiệu hóa theo cơ chế và phạm vi quy định |
| Đã kết thúc vòng đời | Không còn nhu cầu sử dụng; phụ thuộc, thu hồi và hồ sơ đã được xử lý |

Đây không phải trạng thái chuẩn chung; cần định nghĩa tiêu chí vào, ra và bằng chứng cho từng trạng thái trong triển khai.

### 8.1. Xóa tham chiếu không phải thu hồi credential

Xóa một bản ghi trong inventory không làm key ở cloud hoặc mật khẩu ở cơ sở dữ liệu hết hiệu lực. Xóa secret khỏi vault cũng không nhất thiết vô hiệu hóa phương tiện xác thực tại hệ thống đích.

Quy trình ngừng dùng cần xác định nơi credential được chấp nhận, các bản phân phối hợp lệ, consumer, phiên và thông tin xác thực phát sinh. Chỉ chuyển trạng thái sang đã thu hồi khi có bằng chứng theo hợp đồng của cơ chế đích.

Nếu không còn truy cập được hệ thống đích để kiểm chứng, phải giữ rõ trạng thái chưa xác minh hoặc rủi ro còn tồn tại. Không dùng việc mất liên lạc làm bằng chứng rằng credential không còn hoạt động.

### 8.2. Xử lý khi nghi lộ bí mật

Khi credential bị nghi lộ, associated credential giúp xác định nhanh principal, quyền, tài nguyên và consumer chịu ảnh hưởng. Cần nối thông tin này với log để đánh giá những phiên hoặc token đã được tạo.

Trình tự xử lý có thể khác luân chuyển định kỳ: mức độ sự cố có thể đòi hỏi vô hiệu hóa ngay dù gây gián đoạn. Người có thẩm quyền cần quyết định theo tác động, kế hoạch ứng phó và khả năng khôi phục. Inventory cung cấp bản đồ phụ thuộc và bằng chứng cho quyết định đó.

Không chỉ tạo secret mới rồi bỏ quên bản cũ còn hợp lệ. Đồng thời, tránh xóa bằng chứng cần thiết khi cập nhật liên kết hoặc kết thúc phiên.

## 9. Ví dụ: một credential, ba consumer

Giả sử principal `svc-payment-db` được dùng để ghi dữ liệu thanh toán. Credential tương ứng được quản lý trong vault và được ba consumer sử dụng:

- Hai instance của API nhận secret khi khởi động.
- Một tác vụ đối soát ban đêm nhận secret từ cấu hình triển khai.

Nếu inventory chỉ ghi hai instance API, đội vận hành có thể cập nhật chúng thành công, thu hồi mật khẩu cũ rồi cho rằng luân chuyển hoàn tất. Tác vụ ban đêm sau đó có thể thất bại vì vẫn sử dụng phiên bản cũ.

Một bản association đầy đủ hơn cần mô tả cả ba consumer, cách mỗi consumer nhận secret, có cần khởi động lại hoặc triển khai lại hay không, thời điểm xác minh và owner tương ứng.

Quy trình thay đổi cần xét khả năng của cơ sở dữ liệu:

- Nếu hỗ trợ cơ chế chuyển đổi có thời gian chồng lấn, phải giới hạn thời gian chồng lấn và xác minh việc vô hiệu hóa credential cũ.
- Nếu chỉ có một mật khẩu hiện hành, cần trình tự cập nhật và phương án phối hợp phù hợp với ứng dụng.

Không kéo dài vô hạn credential cũ chỉ để chờ một tác vụ hiếm chạy. Có thể dùng phép kiểm chứng an toàn được cho phép, lập lịch xác minh hoặc tổ chức cửa sổ thay đổi phù hợp. Khi chưa đủ bằng chứng, trạng thái cần thể hiện chuyển đổi chưa hoàn tất.

Nếu owner dịch vụ thay đổi trong quá trình này, việc bàn giao cần gồm kế hoạch, trạng thái từng consumer, phiên bản đang dùng và quyết định thu hồi. Đổi một email liên hệ không đủ để chuyển giao trách nhiệm vận hành.

## 10. Bằng chứng sử dụng và thay đổi

Để phục vụ kiểm toán và ứng phó sự cố, cần nối các sự kiện bằng credential ID hoặc định danh tương quan phù hợp, không bằng giá trị bí mật.

Một chuỗi bằng chứng hữu ích gồm:

- Ai hoặc workload nào yêu cầu sử dụng credential, thông qua cơ chế nào.
- Principal đích, tài nguyên và mục đích được duyệt.
- ID credential, phiên bản hoặc định danh key phù hợp với cơ chế.
- Quyết định truy cập, thời điểm, kết quả và tham chiếu phiên PAM nếu có.
- Ai phê duyệt, thực hiện và xác minh việc luân chuyển hoặc thu hồi.
- Trạng thái cập nhật của từng consumer và kết quả xác minh tại đích.

Không bật log debug có thể ghi token, mật khẩu hoặc private key chỉ để tìm lỗi association. Thông tin đường dẫn nội bộ, tên secret và cấu trúc tài nguyên cũng cần được giới hạn người xem theo nhu cầu.

Giữ lịch sử thay đổi owner, principal, nơi quản lý và mục đích sử dụng. Nếu một tham chiếu được đổi sang secret khác hoặc principal khác, cần phát hiện và đánh giá lại association, không coi đó là cập nhật tên hiển thị thông thường.

## 11. Tiêu chí kiểm chứng và rà soát

Khi xây dựng quy trình inventory, có thể dùng các tình huống sau để kiểm chứng cách mô hình hoạt động. Đây là gợi ý kiểm thử cho triển khai, không phải kết quả của một hệ thống cụ thể.

| Tình huống | Điều cần đạt |
| --- | --- |
| Hai tài khoản cùng tên ở hai môi trường | Không ghép sai principal hoặc secret |
| Một principal có nhiều key hợp lệ | Theo dõi từng credential và mục đích sử dụng |
| Một secret được nhiều workload tham chiếu | Thể hiện được các consumer và cách cập nhật |
| Consumer ghim phiên bản cũ | Không kết luận đã chuyển chỉ vì phiên bản hiện hành đổi |
| Có khóa riêng không xuất được | Dùng tham chiếu và quyền sử dụng, không yêu cầu sao chép khóa |
| Workload dùng federation hoặc token ngắn hạn | Không tạo bí mật tĩnh không cần thiết |
| Owner chuyển việc | Có bàn giao và rà soát quyền quản trị liên quan |
| Xóa secret nhưng backend vẫn chấp nhận credential | Chưa đánh dấu thu hồi hoàn tất |
| Collector thiếu dữ liệu consumer hoặc đích | Thể hiện giới hạn và trạng thái cần xác minh |
| Consumer chuyển xong nhưng phiên cũ còn tồn tại | Đánh giá phần truy cập còn lại theo yêu cầu thu hồi |

Rà soát định kỳ nên tập trung vào association chưa xác nhận, credential không có owner hợp lệ, consumer chưa rõ, phiên bản cũ còn được dùng, ngoại lệ quá hạn và độ mới của bằng chứng. Khi tính tỷ lệ bao phủ, cần nói rõ mẫu số là tập credential đã biết hay toàn bộ phạm vi đã được discovery.

Một associated credential được quản lý tốt phải nối được phương tiện xác thực với đúng danh tính, đích, consumer, nơi quản lý và trách nhiệm. Chính các quan hệ đó giúp PAM luân chuyển và thu hồi có kiểm chứng, đồng thời tránh để một trường tham chiếu trong inventory che khuất credential còn hoạt động ngoài quy trình.
