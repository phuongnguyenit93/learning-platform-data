# Phát hiện credential dùng chung

Trong chương **Discovery** của quản lý truy cập đặc quyền (PAM), phát hiện credential dùng chung là việc xác định những nơi nhiều người, workload hoặc tài nguyên phụ thuộc vào cùng một thông tin xác thực, cùng một danh tính, hoặc các bản sao có cùng giá trị bí mật. Ba trường hợp này có liên quan nhưng cần bằng chứng và cách xử lý khác nhau.

Kết quả discovery giúp đánh giá phạm vi ảnh hưởng khi credential bị lộ, khả năng quy trách nhiệm và phụ thuộc cần biết trước khi luân chuyển. Nó là đầu vào để kiểm kê quyền, áp dụng đặc quyền tối thiểu, chuyển sang JIT/JEA, quản lý trong vault và điều tra sự cố. Discovery không tự đồng nghĩa với việc đổi secret, khóa tài khoản hoặc thử đăng nhập bằng credential tìm thấy.

## 1. Kết quả cần đạt

Sau bài học, người học có thể:

- Phân biệt dùng chung tài khoản, dùng chung credential và tái sử dụng giá trị secret.
- Chọn nguồn bằng chứng phù hợp mà không biến kho kiểm kê thành nơi lưu secret.
- Xây dựng quan hệ giữa credential, danh tính, người/workload sử dụng và tài nguyên đích.
- Phân loại kết luận theo độ tin cậy, thời gian quan sát và phần chưa kiểm kê được.
- Ưu tiên rủi ro dựa trên quyền, môi trường, số bên sử dụng và khả năng truy vết.
- Chuẩn bị phương án quản trị tiếp theo có tính đến phụ thuộc và khả năng thu hồi thực tế.

## 2. Làm rõ điều gì đang được dùng chung

Credential có thể gồm mật khẩu, API key, token hoặc private key cùng các thông tin cần để xác thực. Tên người dùng, tên secret, chứng thư công khai và mã đối tượng trong vault không tự chúng đều là bí mật, nhưng có thể giúp liên kết các bằng chứng về cách credential được sử dụng.

| Trường hợp | Ví dụ | Kết luận phù hợp |
|---|---|---|
| Dùng chung tài khoản | Nhiều kỹ sư thao tác dưới danh tính `ops-admin` | Danh tính ở hệ thống đích không phân biệt từng người; cần bằng chứng bổ sung để quy trách nhiệm |
| Dùng chung một credential được quản lý | Hai workload tham chiếu cùng đối tượng, phiên bản và trường secret trong vault | Có phụ thuộc dùng chung đã xác minh ở mức tham chiếu |
| Tái sử dụng giá trị secret | Hai tài khoản khác nhau được đặt cùng một mật khẩu | Có rủi ro lan truyền qua các tài khoản, nhưng cần bằng chứng phù hợp về giá trị |
| Dùng cùng danh tính với credential riêng | Mỗi phiên được cấp một token khác nhau cho cùng service principal | Có dùng chung danh tính; chưa chứng minh cùng token được dùng lại |
| Dùng cùng public key | Nhiều đích tin cậy cùng một public key | Có quan hệ tin cậy chung; chưa chứng minh private key được sao chép tới các đích |
| Tên giống nhau | Nhiều máy có tài khoản `local-maint` | Chưa chứng minh cùng danh tính hoặc cùng mật khẩu |

Một tài khoản dùng chung có thể nằm sau broker PAM, với quyền truy cập theo từng người và ghi nhận phiên đầy đủ. Cơ chế đó cải thiện kiểm soát và truy vết, nhưng danh tính đích vẫn là dùng chung. Báo cáo nên phản ánh đúng cả đặc điểm chia sẻ lẫn mức kiểm soát, thay vì coi credential đã vào vault là không còn rủi ro.

Ngược lại, nhiều workload cùng đọc một secret có thể là thiết kế được tổ chức cho phép. Việc phát hiện quan hệ này chưa đủ để kết luận đã có xâm nhập hoặc vi phạm. Cần đối chiếu với chính sách, phạm vi quyền và chủ sở hữu có trách nhiệm.

## 3. Vì sao cần phát hiện trước khi xử lý credential?

### 3.1. Phạm vi ảnh hưởng khi bị lộ

Nếu một credential có thể truy cập nhiều máy hoặc dịch vụ, lộ ở một nơi có thể tạo khả năng truy cập sang nơi khác. Mức ảnh hưởng còn phụ thuộc vào việc các đích có chấp nhận credential đó, quyền được cấp và điều kiện truy cập. Không chỉ đếm số bản sao mà bỏ qua quyền thực tế.

Dùng chung giữa development và production đặc biệt cần rà soát: môi trường có mức kiểm soát thấp hơn có thể trở thành nơi làm lộ bí mật dùng ở môi trường nhạy cảm. Tuy nhiên, cùng tên secret ở hai môi trường chưa chứng minh giá trị bằng nhau.

### 3.2. Khó quy trách nhiệm

Log đích ghi tài khoản `ops-admin` không tự cho biết kỹ sư nào đang thao tác. Cần nối với xác thực cá nhân, yêu cầu cấp quyền, checkout credential hoặc phiên broker. Nếu người dùng đã nhận giá trị secret và có thể dùng ngoài broker, chỉ có log checkout chưa đủ chứng minh mọi hành động đều được kiểm soát.

### 3.3. Luân chuyển có thể làm gián đoạn

Đổi một secret có ba consumer nhưng chỉ biết hai sẽ làm consumer còn lại lỗi xác thực. Vì vậy, discovery phải xác định phụ thuộc, người chịu trách nhiệm và độ mới của dữ liệu trước khi lập kế hoạch luân chuyển.

Không thấy truy cập gần đây không đủ chứng minh secret không còn cần thiết. Một tác vụ có thể chỉ chạy cuối tháng hoặc chỉ dùng trong khôi phục sự cố. Thiếu log cũng khác với không có sử dụng.

## 4. Đặt phạm vi và thu thập từ nguồn phù hợp

Xác định rõ miền quản lý, môi trường, loại credential, tài nguyên và consumer nằm trong đợt kiểm kê. Danh sách này là mẫu số để đo độ bao phủ, bao gồm cả các đối tượng không truy vấn được.

| Nguồn | Bằng chứng có thể thu | Giới hạn cần ghi nhận |
|---|---|---|
| Metadata vault | Định danh đối tượng, phiên bản, trường credential, quyền truy cập, chủ sở hữu, lịch sử cấp phát | Quyền đọc không chứng minh đã đọc; đã đọc không chứng minh đã dùng thành công |
| Cấu hình triển khai được phép kiểm kê | Consumer tham chiếu secret nào, môi trường nào, đích nào | Cấu hình có thể cũ hoặc khác trạng thái đang chạy |
| Nền tảng quản lý workload | Danh tính workload, lần triển khai, nguồn credential được gắn | Không nhất thiết thấy mọi bản sao hoặc việc dùng ngoài nền tảng |
| Broker/phiên PAM | Người được xác thực, request/grant, danh tính đích, thời điểm và phiên | Cần xác định có đường truy cập trực tiếp ngoài broker không |
| Log xác thực tại đích | Danh tính, thời gian, kết quả, thông tin phiên hoặc credential ID nếu được hỗ trợ | Nhiều hệ thống không cho biết giá trị credential nào đã xác thực |
| Danh mục tài sản và danh tính | Chủ sở hữu, quyền, môi trường, vòng đời | Phải kiểm tra độ mới và đối chiếu với trạng thái thực tế |
| Công cụ phát hiện secret được tổ chức cho phép | Vị trí hoặc loại bí mật có thể tồn tại | Kết quả phát hiện chưa luôn chứng minh secret còn hiệu lực hay là bản sao giống nhau |

Ưu tiên dữ liệu tham chiếu và metadata đã đủ cho mục tiêu. Nếu phải dùng công cụ phát hiện secret, cần xác định phạm vi thu thập và cách che giấu nội dung ngay từ thiết kế. Không đưa giá trị secret vào ticket, bảng kiểm kê, log collector hoặc ví dụ báo cáo.

Danh tính collector chỉ cần quyền đọc đủ cho nguồn được phép. Không tự dùng credential đặc quyền vừa phát hiện để mở rộng quét sang tài nguyên khác. Phát hiện một secret không tạo ra quyền sử dụng nó.

## 5. Thu thập quan hệ thay vì gom một danh sách secret

Một mô hình có ích cần phân biệt ít nhất năm loại đối tượng:

```text
Người/workload sử dụng
        ↓ được phép lấy hoặc được cấp
Credential / phiên bản / trường bí mật
        ↓ xác thực cho
Danh tính tại hệ thống đích
        ↓ nhận quyền trên
Tài nguyên và tập thao tác
```

Mỗi quan hệ nên có loại bằng chứng, nguồn, thời gian và trạng thái xác minh. Ví dụ:

- `CAN_READ`: có quyền đọc secret, chưa chứng minh đã đọc.
- `CONFIGURED_REFERENCE`: cấu hình đang tham chiếu tới credential.
- `RETRIEVED`: đã có sự kiện cấp phát hoặc đọc.
- `PRESENTED_TO_TARGET`: có bằng chứng credential được trình tới đích nếu cơ chế ghi nhận hỗ trợ.
- `AUTHENTICATED_AS`: có sự kiện xác thực thành công dưới danh tính đích.

Không tự biến `CAN_READ` thành `USED`. Cũng không nối `RETRIEVED` với một đăng nhập chỉ vì xảy ra gần nhau nếu không có định danh hoặc ngữ cảnh đủ đáng tin cậy.

### 5.1. Định danh phải bao gồm nguồn và phiên bản

Khóa tham chiếu có thể cần:

```text
credential_authority + object_id + version_id + secret_field
```

Hai vault có cùng đường dẫn không nhất thiết chứa cùng credential. Một đối tượng vault có thể chứa nhiều trường, chẳng hạn username, password và private key; tham chiếu cùng đối tượng nhưng khác trường chưa chứng minh cùng giá trị bí mật.

Alias như `current` hoặc `latest` cần được phân giải tại thời điểm quan sát. Nếu consumer A lấy phiên bản 17 còn consumer B vẫn giữ phiên bản 16, việc cùng tham chiếu alias hiện tại chưa chứng minh cả hai đang dùng cùng phiên bản. Cần tách cấu hình mong muốn, lần cấp phát và trạng thái đã triển khai.

### 5.2. Không gộp danh tính chỉ bằng tên

`svc-backup` trong hai tenant hoặc trên hai máy có thể là hai tài khoản khác nhau. Tương tự, một workload có nhiều replica có thể là nhiều instance của cùng consumer logic hoặc là nhiều consumer được quản trị riêng.

Báo cáo nên nêu đơn vị đếm: người, tài khoản, workload logic, instance, credential hay phiên bản. Việc gộp replica để thống kê không được làm mất thông tin những instance chưa nhận phiên bản mới.

## 6. Mức bằng chứng và độ tin cậy của kết luận

Nên đặt nhãn theo điều đã được chứng minh, tránh một nhãn chung “shared credential” cho mọi tín hiệu.

| Mức kết luận | Ví dụ bằng chứng | Điều phải tránh suy rộng |
|---|---|---|
| Đã xác minh dùng chung danh tính | Nhiều người được xác thực riêng có phiên được liên kết đáng tin cậy tới cùng tài khoản đích | Chưa chứng minh họ giữ cùng một bản sao secret |
| Đã xác minh dùng chung tham chiếu | Hai consumer đang cấu hình cùng authority, object, version và field đã phân giải | Chưa chứng minh mọi consumer đã chạy hoặc secret được dùng thành công |
| Đã xác minh dùng chung credential khi sử dụng | Hệ thống có credential ID/phiên bản và log sử dụng liên kết đáng tin cậy tới nhiều consumer | Không áp dụng kết luận đó cho đích khác chưa quan sát |
| Có bằng chứng tái sử dụng giá trị | Kết quả so sánh được bảo vệ, từ cơ chế được cho phép, phù hợp với loại secret | Không coi mọi dữ liệu băm hoặc chuỗi che giấu giống nhau là bằng chứng |
| Nghi ngờ | Tên, đường dẫn, lịch sử hoặc mẫu triển khai tương tự | Không gắn nhãn đã xác nhận hoặc tự động xử lý phá vỡ vận hành |
| Chưa xác minh | Nguồn thiếu quyền đọc, lỗi hoặc dữ liệu quá cũ | Không kết luận không có chia sẻ |

Kết luận cần đi kèm phạm vi thời gian. Hai consumer dùng phiên bản 16 ở tháng trước không chứng minh chúng vẫn dùng chung phiên bản đó sau khi đã tách danh tính.

### 6.1. Khi nào metadata đủ dùng?

Nếu hai cấu hình đã xác minh cùng trỏ đến đúng một trường của cùng phiên bản credential trong cùng vault, có thể kết luận quan hệ dùng chung tham chiếu mà không đọc giá trị secret. Đây thường là dữ liệu đã đủ để lên danh sách phụ thuộc cần xử lý khi luân chuyển.

Tuy nhiên, hai object khác nhau có thể chứa cùng một giá trị. Chỉ kiểm kê tham chiếu sẽ chưa phát hiện mọi trường hợp tái sử dụng này. Báo cáo cần nêu giới hạn đó thay vì khẳng định không có secret trùng giá trị.

### 6.2. So sánh giá trị bí mật cần một cơ chế riêng được kiểm soát

Không băm mật khẩu bằng một hàm băm nhanh thông thường rồi xuất kết quả vào kho discovery như thể đã loại bỏ rủi ro. Mật khẩu có thể đoán được; một giá trị băm có thể trở thành mục tiêu kiểm tra phỏng đoán ngoại tuyến.

Nếu mục tiêu yêu cầu xác định trùng giá trị, ưu tiên cơ chế được hệ thống quản lý credential hỗ trợ để so sánh bên trong ranh giới tin cậy và chỉ trả kết luận cần thiết. Một thiết kế có thể dùng cơ chế so sánh hoặc dấu so sánh có khóa được bảo vệ, nhưng phải kiểm soát quyền truy vấn, khóa, phạm vi so sánh, tốc độ và thời hạn lưu.

Ngay cả dấu so sánh có khóa cũng không nên được coi là dữ liệu công khai. Lộ khóa hoặc có một dịch vụ cho phép thử giá trị tùy ý có thể làm suy yếu cơ chế. Việc so sánh giữa các miền còn cần quyết định rõ về quyền riêng tư và phạm vi quản trị.

Các password hash lấy từ hệ thống xác thực có thuật toán, salt hoặc tham số khác nhau không thể được so sánh đơn giản để kết luận mật khẩu có giống nhau hay không. Bài discovery này không yêu cầu trích xuất hash hoặc giải mã secret để tự xây một kho so sánh.

### 6.3. Public key, private key và chứng thư

Với public key, fingerprint tính trên biểu diễn công khai được chuẩn hóa có thể giúp nhận diện cùng khóa công khai. Với chứng thư, fingerprint toàn bộ chứng thư và fingerprint khóa công khai trả lời hai câu hỏi khác nhau; hai chứng thư khác nhau vẫn có thể chứa cùng public key.

Cùng public key xuất hiện trong cấu hình tin cậy của nhiều máy có thể cho thấy cùng chủ thể giữ private key có đường truy cập đến nhiều máy. Điều này không chứng minh private key đã được sao chép tới các máy đích. Phải phân biệt **nơi chấp nhận khóa** với **nơi giữ khóa bí mật**.

Không thu private key để tạo fingerprint trong kho discovery thông thường. Dùng metadata quản lý khóa hoặc dấu nhận diện công khai phù hợp khi có thể đáp ứng mục tiêu.

## 7. Quy trình discovery tham khảo

### Bước 1: Chốt phạm vi và định nghĩa kết luận

Xác định loại chia sẻ cần phát hiện: tài khoản đích dùng chung, tham chiếu credential dùng chung hay tái sử dụng giá trị. Ghi rõ nguồn nào có thể chứng minh từng loại và những phần không thể xác minh trong đợt này.

### Bước 2: Thu metadata và liên kết consumer

Thu định danh credential, phiên bản, trường, quyền cấp phát và các consumer từ nguồn đã cho phép. Phân giải alias theo thời điểm. Lưu trạng thái lỗi, consumer chưa truy vấn được và bản ghi đã cũ.

### Bước 3: Liên kết danh tính và tài nguyên đích

Xác định credential xác thực cho tài khoản nào, ở đâu và với quyền gì. Một credential có cùng tên trong vault nhưng không còn được đích chấp nhận cần được phân loại khác với credential đang hoạt động. Không tự thử đăng nhập để bù cho thiếu bằng chứng.

### Bước 4: Tạo nhóm theo đúng loại bằng chứng

Nhóm theo tham chiếu đã xác minh, danh tính đích hoặc kết quả so sánh được phép. Không trộn các nhóm này thành một nhóm “cùng giá trị secret”. Giữ cạnh quan hệ để biết vì sao các đối tượng được liên kết.

### Bước 5: Xác nhận mục đích và phụ thuộc

Tra chủ sở hữu, luồng cấp phát, tần suất công việc và lý do dùng chung. Với tài khoản dịch vụ, xác định nơi nạp credential, bộ nhớ đệm, tác vụ định kỳ và cơ chế cập nhật. Nếu một consumer chưa được kiểm kê, giữ nó là khoảng trống cần xử lý.

### Bước 6: Đánh giá rủi ro và chuyển việc

Lập phát hiện có phạm vi, bằng chứng, độ tin cậy, tác động và đề xuất. Chuyển sang luồng quản trị credential hoặc ứng phó sự cố phù hợp; không tự đổi secret hay xóa quyền trong discovery.

Logic nhóm tham chiếu dưới đây là **mã giả**, không truy cập hoặc xử lý giá trị secret:

```text
for observation in authorized_observations:
    if observation.is_stale or observation.reference_is_unresolved:
        record_visibility_gap(observation)
        continue

    key = (
        observation.credential_authority,
        observation.object_id,
        observation.resolved_version_id,
        observation.secret_field
    )

    add_evidence_edge(key, observation.consumer_id,
                      observation.evidence_type,
                      observation.observed_at)

for credential_reference in grouped_references:
    consumers = distinct_consumers_with_verified_configuration(
        credential_reference
    )
    if count(consumers) > 1:
        report_shared_reference(
            credential_reference,
            consumers,
            limitation = 'does not prove successful use or all value reuse'
        )
```

## 8. Ví dụ: ba workload cùng tham chiếu một mật khẩu dịch vụ

Giả sử danh tính `svc-orders-db` có quyền trên cơ sở dữ liệu production. Hai workload của orders và một runner dùng chung trong môi trường phát triển đều có cấu hình tham chiếu phiên bản 17 của cùng trường mật khẩu trong vault.

Bản ghi sau là **YAML minh họa mô hình phát hiện**, không phải cấu hình của một sản phẩm:

```yaml
finding_id: SHARED-007
finding_type: shared_credential_reference
credential_reference:
  authority: vault-prod-acme
  object_id: cred-073
  resolved_version_id: '17'
  secret_field: db_password
target_identity:
  authority: database-prod-acme
  principal_id: svc-orders-db
consumers:
  - id: workload-orders-api
    environment: production
    evidence: verified_runtime_configuration
  - id: workload-orders-batch
    environment: production
    evidence: verified_runtime_configuration
  - id: runner-dev-shared
    environment: development
    evidence: verified_runtime_configuration
observed_at: '2026-11-26T10:00:00+07:00'
secret_value_collected: false
conclusion: confirmed_reference_sharing
successful_use_by_all_consumers: unverified
owner_confirmation: pending
limitations:
  - credential_copies_outside_managed_sources_not_fully_visible
  - authentication_logs_do_not_expose_credential_version
```

Có thể kết luận ba consumer đã quan sát cùng tham chiếu credential. Cần ưu tiên xác minh vì một consumer development liên quan đến credential của danh tính production. Chưa thể kết luận runner đã đăng nhập thành công hoặc credential đã bị đánh cắp.

Giả sử vault còn có sự kiện một kỹ sư đọc phiên bản 17. Sự kiện này thêm bằng chứng credential đã được cấp phát cho người đó. Nó chưa chứng minh người đó lưu bản sao lâu dài, cũng không tự chứng minh mọi đăng nhập dưới `svc-orders-db` đều do người đó thực hiện.

### Câu hỏi cần giải quyết tiếp

1. Runner development có thực sự cần quyền này hay là cấu hình còn sót?
2. Quyền cấp phát ở vault và quyền đăng nhập tại đích có được giới hạn theo consumer không?
3. Có thể tách danh tính API, batch và hoạt động quản trị của con người không?
4. Consumer nào đang giữ bản sao hoặc bộ nhớ đệm phiên bản 17?
5. Có tác vụ ít chạy chưa xuất hiện trong cửa sổ quan sát không?
6. Nếu đổi credential, cách cập nhật, xác minh và thu hồi credential cũ là gì?

Các câu hỏi này tạo đầu vào cho việc tách danh tính và luân chuyển có kiểm soát. Không giải quyết bằng cách xóa quyền runner hoặc đổi ngay mật khẩu trong phạm vi một tác vụ chỉ được giao discovery.

## 9. Đánh giá rủi ro và tránh kết luận sai

| Yếu tố | Dấu hiệu cần ưu tiên | Bằng chứng bổ sung |
|---|---|---|
| Quyền của danh tính | Quản trị hệ thống, đọc secret khác hoặc sửa quyền | Quyền hiệu lực và tài nguyên đích |
| Ranh giới môi trường | Dùng chung giữa production và môi trường ít kiểm soát hơn | Tham chiếu, cấp phát, quyền truy cập và cấu hình thực tế |
| Số bên có thể lấy secret | Nhiều người hoặc workload, chủ sở hữu không rõ | Quyền vault, lịch sử cấp phát và danh tính gốc |
| Khả năng quy trách nhiệm | Chỉ có tài khoản chung, thiếu liên kết tới phiên cá nhân | Log broker, grant, xác thực và đường truy cập ngoài PAM |
| Khả năng thu hồi | Secret sống lâu, bản sao ngoài quản lý, không biết consumer | Phiên bản đang dùng, cache, token/phiên phát sinh |
| Độ tin cậy dữ liệu | Dữ liệu cũ hoặc thiếu nguồn quan trọng | Thời gian thu, trạng thái lỗi và kế hoạch bổ sung |

### Những tín hiệu không đủ để xác nhận dùng chung giá trị

- Hai bản ghi cùng hiển thị `********`: đây có thể chỉ là chuỗi che giấu cố định.
- Hai tài khoản cùng tên hoặc cùng mẫu đặt tên.
- Hai secret có cùng mô tả, chủ sở hữu hoặc ngày tạo.
- Nhiều đăng nhập từ cùng IP: có thể qua NAT, proxy hoặc broker.
- Một tài khoản xuất hiện từ nhiều địa chỉ: có thể là nhiều instance hợp lệ.
- Hai token cùng subject: chúng có thể là credential khác nhau, có phiên và thời hạn riêng.
- Secret có quyền đọc rộng: đó là khả năng tiếp cận, chưa phải bằng chứng mọi người đã lấy secret.

Tương quan thời gian và địa chỉ có thể hỗ trợ điều tra nhưng không nên được trình bày như chứng minh trực tiếp về giá trị credential. Cần giữ nguyên mức kết luận phù hợp với bằng chứng.

## 10. Từ phát hiện sang quản trị PAM

Các hướng xử lý tùy trường hợp gồm tách danh tính theo người/workload, cấp credential ngắn hạn, thu hẹp thao tác và tài nguyên, dùng broker, hạn chế xuất secret, hoặc luân chuyển credential đang dùng chung. Quyết định cần tính đến khả năng của hệ thống đích và phụ thuộc đã kiểm kê.

### 10.1. Với tài khoản quản trị của con người

Ưu tiên xác thực cá nhân và quyền theo công việc. Nếu vẫn phải dùng danh tính đích chung, cần ràng buộc từng lần sử dụng với cá nhân, yêu cầu, thời hạn và phiên; đồng thời kiểm soát đường truy cập trực tiếp. JIT/JEA chỉ có ý nghĩa thực tế khi grant có đúng phạm vi và quyền thường trực còn lại đã được đánh giá.

### 10.2. Với tài khoản dịch vụ và workload

Tách danh tính khi cần phân biệt quyền, vòng đời hoặc trách nhiệm của từng consumer. Không chia sẻ secret quản trị cho con người chỉ vì workload đang dùng secret đó. Nơi có khả năng hỗ trợ, có thể sử dụng danh tính workload hoặc credential cấp động với phạm vi phù hợp.

Cần hiểu cách workload nạp lại credential. Có hệ thống đọc một lần lúc khởi động, có hệ thống dùng cache hoặc kết nối sống lâu. Cập nhật giá trị ở vault không tự bảo đảm mọi instance đã chuyển sang phiên bản mới.

### 10.3. Với kế hoạch luân chuyển

Trước khi thực hiện thay đổi được phép, cần biết danh sách consumer, chủ sở hữu, cách phân phối phiên bản mới, điều kiện xác minh và cách xử lý lỗi. Nếu hệ thống hỗ trợ giai đoạn chồng lấn, phải có thời hạn rõ ràng và theo dõi để phiên bản cũ không tồn tại vô hạn.

Đổi mật khẩu hoặc thu hồi một API key không mặc nhiên vô hiệu hóa mọi token hay phiên đã tạo trước đó. Cần xác minh cơ chế của đích và xử lý những quyền còn hiệu lực. Nếu đã có dấu hiệu lộ credential, sử dụng luồng ứng phó sự cố để quyết định tốc độ, phạm vi thu hồi và bảo toàn bằng chứng.

Đóng một phát hiện không chỉ bằng việc ghi “đã đổi secret”. Cần chứng minh mục tiêu đã đạt: các consumer đã tách hoặc được kiểm soát theo thiết kế, credential cũ được xử lý, quyền còn lại phù hợp và phạm vi chưa quan sát được đã được nêu rõ.

## 11. Bằng chứng, độ bao phủ và chỉ số

Một phát hiện cần có ít nhất:

- Định danh phát hiện và loại chia sẻ đã được chứng minh.
- Credential reference hoặc dấu nhận diện được phép, không có giá trị secret.
- Danh tính đích, tài nguyên, quyền và các consumer liên quan.
- Loại quan hệ, nguồn, thời gian quan sát và cách liên kết bằng chứng.
- Chủ sở hữu, mức độ tin cậy, giới hạn và khoảng trống thu thập.
- Rủi ro, việc cần xử lý tiếp và tiêu chí xác minh sau thay đổi.

Dữ liệu quan hệ này có thể tiết lộ đường truy cập nhạy cảm. Cần hạn chế người xem/sửa, bảo vệ tính toàn vẹn và có thời gian lưu phù hợp. Nếu đầu ra công cụ vô tình chứa secret, phải xử lý theo quy trình phù hợp thay vì sao chép nó sang báo cáo để minh họa.

### Chỉ số cần có mẫu số

```text
Độ bao phủ consumer =
    số consumer trong phạm vi có dữ liệu tham chiếu còn đủ mới
    / tổng số consumer trong phạm vi

Độ đầy đủ liên kết đích =
    số credential reference có ánh xạ danh tính và tài nguyên đã xác minh
    / tổng số credential reference cần xác minh trong phạm vi
```

Ví dụ, có sáu consumer trong phạm vi nhưng chỉ thu đủ dữ liệu mới của năm consumer thì độ bao phủ là `5/6`. Không loại consumer lỗi khỏi mẫu số. Nếu phát hiện nhóm ba consumer dùng chung tham chiếu, số đó là số đã quan sát; chưa chứng minh không có consumer thứ tư trong phần chưa thấy.

Có thể thống kê số danh tính dùng chung, nhóm tham chiếu dùng chung, credential bị xác nhận tái sử dụng giá trị và phát hiện chưa có chủ sở hữu. Cần tách các chỉ số này, tránh đếm chúng như một loại bằng chứng duy nhất hoặc cộng trùng một phát hiện theo nhiều đường liên kết.

Số nhóm chia sẻ giảm sau một đợt thu thất bại không chứng minh rủi ro giảm. Đánh giá xu hướng phải đi cùng độ bao phủ, độ mới và thay đổi phương pháp.

## 12. Bài tập và kiểm thử chấp nhận

### Tình huống

Hai workload production tham chiếu cùng một phiên bản mật khẩu. Một runner development tham chiếu alias của đối tượng đó, nhưng chưa xác minh nó đã nhận phiên bản nào. Hai tài khoản quản trị cục bộ trên hai máy có cùng tên. Log cơ sở dữ liệu chỉ ghi username và địa chỉ nguồn, không ghi credential ID.

### Yêu cầu thực hành

1. Vẽ các đối tượng và quan hệ, phân biệt cấu hình, cấp phát và xác thực thành công.
2. Chỉ ra phần nào đủ để kết luận dùng chung tham chiếu, phần nào còn chưa xác minh.
3. Giải thích vì sao hai tài khoản cục bộ cùng tên chưa chứng minh cùng mật khẩu.
4. Liệt kê metadata tối thiểu cần thêm để đánh giá runner mà không đọc secret.
5. Đề xuất việc cần làm trước khi lập kế hoạch luân chuyển cho hai workload production.
6. Viết một phát hiện không chứa secret, có độ tin cậy và giới hạn quan sát rõ ràng.

### Hướng giải tham khảo

Hai workload production có bằng chứng về cùng tham chiếu phiên bản đã xác minh. Runner cần phân giải alias và đối chiếu dữ liệu triển khai hoặc cấp phát trước khi gộp vào nhóm cùng phiên bản. Log username và IP hỗ trợ đánh giá hoạt động nhưng không đủ xác định giá trị mật khẩu đã dùng. Hai tài khoản cục bộ phải giữ định danh riêng; kết luận tái sử dụng mật khẩu vẫn chưa được chứng minh.

Trước luân chuyển, xác nhận chủ sở hữu, consumer ít chạy, cách nạp credential, token/phiên liên quan và cơ chế thu hồi. Việc thu thập này tạo căn cứ cho một thay đổi riêng được quản lý, không tự thực hiện thay đổi trong discovery.

### Ma trận nghiệm thu

Dùng dữ liệu tổng hợp hoặc môi trường thực hành được phép; không đưa credential thật vào bộ dữ liệu kiểm thử.

| Ca kiểm tra | Kết quả cần đạt |
|---|---|
| Hai consumer cùng authority, object, version và field đã xác minh | Phát hiện dùng chung tham chiếu; không tự khẳng định đã dùng thành công |
| Cùng đường dẫn nhưng khác vault hoặc tenant | Không tự gộp thành cùng credential |
| Cùng object nhưng khác trường secret | Giữ các tham chiếu riêng, đánh giá theo nội dung trường được quản lý |
| Cùng alias nhưng phiên bản ở consumer chưa rõ | Ghi chưa xác minh phiên bản, không gộp chắc chắn |
| Hai tài khoản cùng tên trên hai máy | Không suy ra cùng danh tính hoặc cùng mật khẩu |
| Đầu ra hai nơi đều là chuỗi che giấu | Không coi là bằng chứng giá trị bằng nhau |
| Hai token khác nhau cho cùng chủ thể | Phân loại dùng chung danh tính nếu phù hợp, không kết luận cùng token |
| Cùng public key được tin cậy ở nhiều đích | Phân biệt nơi chấp nhận khóa với nơi giữ private key |
| Nhiều phiên cá nhân qua broker dùng cùng tài khoản đích | Ghi danh tính đích dùng chung và giữ liên kết cá nhân–phiên |
| Nguồn thu thập lỗi hoặc dữ liệu quá cũ | Giữ khoảng trống, không trả kết luận không có chia sẻ |
| Sau xử lý, credential cũ vẫn còn phiên hiệu lực | Chưa coi mục tiêu thu hồi đã hoàn tất |
| Kiểm tra báo cáo và log collector | Không có mật khẩu, token, private key hoặc nội dung secret |

Một kết quả discovery có ích phải nói rõ điều gì được dùng chung, ai hoặc workload nào liên quan, tại tài nguyên nào và dựa trên loại bằng chứng nào. Những phần chưa xác minh cần trở thành công việc cụ thể để giảm rủi ro và chuẩn bị quản trị credential an toàn.